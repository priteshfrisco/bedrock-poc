#!/usr/bin/env python3
"""
UNIFIED ORCHESTRATOR - Local or AWS Cloud Processing
Supports both local file processing and S3/cloud processing
"""

import pandas as pd
import json
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import traceback
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import openai

# Import pipeline components
from src.llm.gpt_client import GPTClient
from src.llm.prompt_builder import build_complete_prompt
from src.llm.tools import INGREDIENT_TOOL
from src.llm.tools.ingredient_lookup import lookup_ingredient
from src.llm.tools.health_focus_lookup import lookup_health_focus
from src.pipeline.utils.unit_converter import process_product_attributes
from src.pipeline.utils.business_rules import apply_all_business_rules
from src.pipeline.utils.high_level_category import assign_high_level_category
from src.utils.preprocessing import is_non_supplement, standardize_dataframe
from src.core.log_manager import LogManager
from src.utils.file_utils import write_csv
from src.core.file_tracker import FileTracker
from src.utils.result_builder import build_error_result, build_success_result, build_filtered_result
from src.pipeline.step1_filter import generate_step1_audits, apply_step1_filter
from src.pipeline.step2_llm import extract_llm_attributes, extract_attributes_from_llm_result, extract_metadata_from_llm_result
from src.pipeline.step3_postprocess import apply_postprocessing

# AWS imports (only loaded in AWS mode)
try:
    import boto3
    from src.aws.s3_manager import S3Manager
    from src.aws.dynamodb_manager import DynamoDBManager
    from src.aws.notification import (
        send_notification,
        send_success_notification,
        send_error_notification,
        send_invalid_filename_notification,
        send_processing_started_notification
    )
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False


def process_single_record(record: Dict, product_id: int, log_manager, max_retries: int = 3, test_step1_only: bool = False) -> Dict:
    """Process a single record through the complete pipeline - ORCHESTRATION ONLY"""
    start_time = datetime.now()
    asin = record.get('asin', f'P{product_id}')
    title = record.get('title', '')
    amazon_subcat = record.get('amazon_subcategory', '').lower().strip()
    
    result = {
        'product_id': product_id,
        'asin': asin,
        'title': title,
        'brand': record.get('brand', ''),
        'source_subcategory': amazon_subcat,
        'status': 'processing',
        'step_completed': 0
    }
    
    try:
        # ========== STEP 1: NON-SUPPLEMENT FILTERING ==========
        step1_result = apply_step1_filter(title, amazon_subcat, asin, log_manager)
        
        if not step1_result['passed']:
            # Filtered out - add "Step 1 Filter:" prefix to reasoning
            filter_type = step1_result['filter_type']
            raw_reason = step1_result['filter_reason']
            
            if filter_type == 'filtered_by_remove':
                detailed_reason = f"Step 1 Filter: Amazon subcategory marked as REMOVE - {raw_reason}"
            elif filter_type == 'filtered_by_keyword':
                detailed_reason = f"Step 1 Filter: {raw_reason}"
            else:
                detailed_reason = f"Step 1 Filter: {raw_reason}"
            
            result = build_filtered_result(
                result,
                detailed_reason,
                filter_type,
                start_time,
                lookup_action=step1_result.get('action')
            )
            # 💾 Save Step 1 result immediately
            log_manager.save_audit_json('step1_filter', result, f"{asin}.json")
            return result
        
        # Passed filtering - store lookup action details
        result['lookup_action'] = step1_result['action']
        if step1_result['action'] == 'REMAP':
            result['nw_category'] = step1_result['nw_category']
            result['nw_subcategory'] = step1_result['nw_subcategory']
            result['remap_reason'] = step1_result['remap_reason']
        
        log_manager.log_step('step1_filter', f"[{asin}] PASSED filtering")
        
        # ⚠️  TEST MODE: Stop after Step 1 if flag is set
        if test_step1_only:
            result['status'] = 'step1_complete'
            result['step_completed'] = 1
            result['processing_time_sec'] = (datetime.now() - start_time).total_seconds()
            # 💾 Save Step 1 result immediately
            log_manager.save_audit_json('step1_filter', result, f"{asin}.json")
            return result
        
        # ========== STEP 2: LLM EXTRACTION ==========
        llm_extraction_result = extract_llm_attributes(title, asin, product_id, log_manager, max_retries)
        
        if not llm_extraction_result['success']:
            result = build_error_result(result, llm_extraction_result['error'], 2, start_time)
            # 💾 Save Step 2 error immediately
            log_manager.save_audit_json('step2_llm', result, f"{asin}.json")
            return result
        
        llm_result = llm_extraction_result['data']
        
        # Extract attributes
        attributes = extract_attributes_from_llm_result(llm_result)
        age = attributes['age']
        gender = attributes['gender']
        form = attributes['form']
        organic = attributes['organic']
        potency = attributes['potency']
        
        # ========== LLM SAFETY CHECK: If LLM returned REMOVE for any attribute, filter this product ==========
        if age == 'REMOVE' or gender == 'REMOVE' or form == 'REMOVE':
            log_manager.log_step('step2_llm', f"[{asin}] LLM detected non-supplement (returned REMOVE for attributes)")
            detailed_reason = "Step 2 LLM Filter: LLM detected non-supplement product (safety check)"
            filter_result = build_filtered_result(
                result,
                detailed_reason,
                'filtered_by_llm',
                start_time,
                lookup_action='UNKNOWN'
            )
            # 💾 Save LLM filter result immediately
            log_manager.save_audit_json('step2_llm', filter_result, f"{asin}.json")
            return filter_result
        
        # Process size/count/unit
        llm_result = process_product_attributes(llm_result)
        attributes = extract_attributes_from_llm_result(llm_result)
        count = attributes['count']
        unit = attributes['unit']
        size = attributes['size']
        ingredients = attributes['ingredients']
        business_rules = attributes.get('business_rules', {})
        
        # Extract metadata
        metadata = extract_metadata_from_llm_result(llm_result)
        
        # Build Step 2 result and save
        step2_result = result.copy()
        step2_result['status'] = 'step2_complete'
        step2_result['step_completed'] = 2
        step2_result['age'] = age
        step2_result['gender'] = gender
        step2_result['form'] = form
        step2_result['organic'] = organic
        step2_result['count'] = count
        step2_result['unit'] = unit
        step2_result['size'] = size
        step2_result['potency'] = potency
        step2_result['ingredients'] = ingredients
        step2_result['tokens_used'] = metadata['tokens_used']
        step2_result['api_cost'] = metadata['api_cost']
        step2_result['_metadata'] = metadata['_metadata']
        step2_result['processing_time_sec'] = (datetime.now() - start_time).total_seconds()
        # 💾 Save Step 2 result immediately
        log_manager.save_audit_json('step2_llm', step2_result, f"{asin}.json")
        
        # ========== STEP 3: POST-PROCESSING ==========
        # Business rules already applied by LLM, but still get health focus and high level category
        postprocess_result = apply_postprocessing(ingredients, age, gender, title, asin, log_manager)
        
        # Use business_rules from LLM if available, otherwise use postprocess_result
        if business_rules and business_rules.get('final_category'):
            category = business_rules.get('final_category')
            subcategory = business_rules.get('final_subcategory')
            primary_ingredient = business_rules.get('primary_ingredient')
            business_rules_reasoning = business_rules.get('reasoning', '')
            initial_category = business_rules.get('initial_category', category)
            initial_subcategory = business_rules.get('initial_subcategory', subcategory)
            has_changes = business_rules.get('has_changes', False)
            has_unknown = business_rules.get('has_unknown', False)
            
            # Log if changes were made
            if has_changes:
                log_manager.log_step(
                    'step3_postprocess',
                    f"[{asin}] Business rules changed: {initial_category}/{initial_subcategory} → {category}/{subcategory}"
                )
            if has_unknown:
                log_manager.log_step('step3_postprocess', f"[{asin}] WARNING: Contains UNKNOWN values")
        else:
            # Fallback: If LLM extracted 0 ingredients, business rules returns None
            # Use Step 1's NW Category/Subcategory from Amazon lookup if available
            if result.get('nw_category') and result.get('nw_subcategory'):
                category = result['nw_category']
                subcategory = result['nw_subcategory']
                primary_ingredient = 'UNKNOWN'
                business_rules_reasoning = 'No ingredients extracted - using Step 1 Amazon category'
                log_manager.log_step('step3_postprocess', f"[{asin}] No ingredients extracted, using Step 1 category: {category}/{subcategory}")
            else:
                # Final fallback to Python business rules
                category = postprocess_result['category']
                subcategory = postprocess_result['subcategory']
                primary_ingredient = postprocess_result['primary_ingredient']
                business_rules_reasoning = ''
                log_manager.log_step('step3_postprocess', f"[{asin}] WARNING: LLM did not call business_rules tool, using Python fallback")
            has_changes = False
            has_unknown = False
        
        # Build final result
        result['status'] = 'success'
        result['step_completed'] = 3
        result['age'] = age
        result['gender'] = gender
        result['form'] = form
        result['organic'] = organic
        result['count'] = count
        result['unit'] = unit
        result['size'] = size
        result['potency'] = potency
        result['primary_ingredient'] = primary_ingredient
        result['num_ingredients'] = len(ingredients)
        
        # Store all ingredients (up to 20) like R system
        result['all_ingredients'] = []
        for idx, ing in enumerate(ingredients):
            ing_name = ing.get('name', '') if isinstance(ing, dict) else ing
            result['all_ingredients'].append(ing_name)
        
        result['category'] = category
        result['subcategory'] = subcategory
        result['health_focus'] = postprocess_result['health_focus']
        result['high_level_category'] = postprocess_result['high_level_category']
        
        # Add reasoning from business rules (only if changes were made or has unknown)
        result['business_rules_reasoning'] = business_rules_reasoning if (has_changes or has_unknown) else ''
        # Add unified reasoning field - use business_rules_reasoning or default message
        result['reasoning'] = result['business_rules_reasoning'] if result['business_rules_reasoning'] else f"Category: {category}, Subcategory: {subcategory}"
        result['has_business_rule_changes'] = has_changes
        result['has_unknown_values'] = has_unknown
        
        result['tokens_used'] = metadata['tokens_used']
        result['api_cost'] = metadata['api_cost']
        result['_metadata'] = metadata['_metadata']
        result['processing_time_sec'] = (datetime.now() - start_time).total_seconds()
        
        # 💾 Save Step 3 (final) result immediately
        log_manager.save_audit_json('step3_postprocess', result, f"{asin}.json")
        
        log_manager.log_step('step3_postprocess', f"[{asin}] COMPLETE in {result['processing_time_sec']:.2f}s")
        
        return result
        
    except Exception as e:
        log_manager.log_step('error', f"[{asin}] EXCEPTION: {str(e)[:200]}")
        result['traceback'] = traceback.format_exc()
        error_result = build_error_result(result, str(e), result.get('step_completed', 0), start_time)
        # 💾 Save error immediately
        log_manager.save_audit_json('errors', error_result, f"{asin}.json")
        return error_result


def save_results(output_dir: Path, results: List[Dict], input_filename: str, log_manager: LogManager):
    """Save results to CSV only (simplified column set)"""
    log_manager.log_step('step4_output', f"Saving {len(results)} results to CSV...")
    
    df = pd.DataFrame([
        {
            # Core Output Columns (matching R system + Master Item File structure)
            'RetailerSku': r.get('asin', ''),  # Original ASIN from input
            'UPC': '',  # Empty - manual lookup required
            'Description': r['title'],
            'Brand': r['brand'],
            'NW Category': r.get('category', ''),
            'NW Subcategory': r.get('subcategory', ''),
            'NW Sub Brand 1': '',  # Empty - manual entry (NW/IT only)
            'NW Sub Brand 2': '',  # Empty - manual entry (NW/IT only)
            'NW Sub Brand 3': '',  # Empty - manual entry (NW/IT only)
            'Potency': r.get('potency', ''),  # LLM extracted (probiotics mostly)
            'FORM': r.get('form', ''),
            'AGE': r.get('age', ''),
            'GENDER': r.get('gender', ''),
            'COMPANY': r['brand'],  # Default to brand, manual refinement for parent companies
            'FUNCTIONAL INGREDIENT': r.get('primary_ingredient', ''),
            'HEALTH FOCUS': r.get('health_focus', ''),
            'SIZE': r.get('size', ''),
            'HIGH LEVEL CATEGORY': r.get('high_level_category', ''),
            'NW_UPC': '',  # Empty - manual lookup (NW/IT internal UPC only)
            'Unit of Measure': r.get('unit', ''),
            'Pack Count': r.get('count', ''),
            'Organic': r.get('organic', ''),
            # Reasoning: Populated from 'reasoning' field (includes filter reason, LLM detection, or business rules)
            'Reasoning': r.get('reasoning', '')
            
            # NOTE: Multiple ingredients are stored in audit JSON files only, not in CSV
            # NOTE: Tracking columns (Product_ID, Status, Tokens, Cost, Time, Errors, etc.)
            # are also stored in audit JSON files only, not in the CSV output
        }
        for r in results
    ])
    
    # Create output filename: remove "uncoded_" prefix and add "_coded" suffix
    # Example: uncoded_100_records -> 100_records_coded.csv
    if input_filename.lower().startswith('uncoded_'):
        base_name = input_filename[8:]  # Remove "uncoded_" prefix
    else:
        base_name = input_filename
    
    output_filename = f"{base_name}_coded.csv"
    csv_file = output_dir / output_filename
    df.to_csv(csv_file, index=False)
    
    log_manager.log_step('step4_output', f"Saved CSV: {csv_file} ({len(results)} records)")
    log_manager.log_step('step4_output', f"CSV has {len(df.columns)} columns")
    
    return csv_file


def save_audit_step_files(log_manager: LogManager, results: List[Dict], step: str):
    """Save per-product audit files for a specific step - Named by ASIN for easy tracking"""
    for result in results:
        asin = result.get('asin', f"P{result['product_id']:04d}")  # Fallback to product_id if no ASIN
        log_manager.save_audit_json(
            step_name=step,
            data=result,
            filename=f"{asin}.json"
        )


def main():
    print("="*80)
    print("PRODUCTION ORCHESTRATOR - PROCESS 1000+ RECORDS")
    print("="*80)
    
    start_time = datetime.now()
    print(f"\nStart Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Configuration
    import sys
    INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else 'data/input/uncoded_100_records.csv'  # Allow command line override
    MAX_WORKERS = 1000  # Number of parallel threads for maximum speed
    BATCH_SIZE = 1000  # Save results every 1000 records (faster processing)
    
    # ⚠️  TEST MODE: Stop after Step 1 (filtering only)
    TEST_STEP1_ONLY = False  # Run complete pipeline (Steps 1, 2, 3)  # Set to False to run full pipeline
    
    print(f"\nConfiguration:")
    print(f"   Input File: {INPUT_FILE}")
    print(f"   Max Workers: {MAX_WORKERS} (parallel API calls)")
    print(f"   Batch Size: {BATCH_SIZE} (save every N records)")
    
    # Load data
    print(f"\nLoading data...")
    raw_df = pd.read_csv(INPUT_FILE, encoding='latin-1')
    print(f"✓ Loaded {len(raw_df):,} raw records")
    
    # Standardize columns (rename, lowercase, clean)
    print(f"Standardizing columns...")
    df = standardize_dataframe(raw_df)
    records = df.to_dict('records')
    total_records = len(records)
    
    print(f"✓ Standardized {total_records:,} records")
    
    # Extract input filename (without path and extension)
    input_filename = Path(INPUT_FILE).stem  # e.g., "sample_10_test"
    
    # ✓ VALIDATE: File must start with "uncoded_"
    if not input_filename.lower().startswith('uncoded_'):
        print(f"\n⚠ ERROR: Input file must start with 'uncoded_'")
        print(f"   Got: {input_filename}")
        print(f"   Expected: uncoded_*.csv")
        print(f"\nExample valid filenames:")
        print(f"   - uncoded_products.csv")
        print(f"   - uncoded_january_2026.csv")
        print(f"   - UNCODED_test.csv")
        sys.exit(1)
    
    # Initialize LogManager (handles all logging and audit structure)
    log_manager = LogManager(input_filename=input_filename, base_path='data')
    info = log_manager.get_info()
    
    # Initialize FileTracker (simple file-level status tracking)
    file_tracker = FileTracker()
    
    # Check if file is already being processed
    if not file_tracker.can_process(input_filename):
        print(f"⚠ ERROR: File {input_filename} is already being processed!")
        return
    
    # Mark file as processing
    file_tracker.mark_processing(input_filename, info['run_id'], total_records)
    
    log_manager.log_step('run', "="*80)
    log_manager.log_step('run', f"STARTING PRODUCTION ORCHESTRATOR")
    log_manager.log_step('run', "="*80)
    log_manager.log_step('run', f"Input file: {INPUT_FILE}")
    log_manager.log_step('run', f"Total records: {total_records}")
    log_manager.log_step('run', f"Max workers: {MAX_WORKERS}")
    log_manager.log_step('run', f"Batch size: {BATCH_SIZE}")
    log_manager.log_step('run', f"File ID: {info['file_id']}")
    log_manager.log_step('run', f"Run ID: {info['run_id']}")
    
    # Initialize step-specific logs
    log_manager.log_step_start('step1_filter', 'STEP 1: NON-SUPPLEMENT FILTERING')
    log_manager.log_step_start('step2_llm', 'STEP 2: LLM EXTRACTION')
    log_manager.log_step_start('step3_postprocess', 'STEP 3: POST-PROCESSING (Business Rules, HF, HLC)')
    log_manager.log_step_start('step4_output', 'STEP 4: OUTPUT GENERATION')
    
    # Create output directory: data/output/{file_id}/run_{num}/
    output_dir = Path(f"data/output/{info['file_id']}/{info['run_id']}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Output Directory: {output_dir}")
    print(f"📁 Logs Directory: {info['logs_path']}")
    print(f"📁 Audit Directory: {info['audit_path']}")
    print(f"📁 Tracking: data/tracking/{info['file_id']}_*.json")
    
    # Process records in parallel
    if TEST_STEP1_ONLY:
        print(f"\n⚠️  TEST MODE: Running Step 1 (Filtering) ONLY")
        print(f"   LLM extraction will be SKIPPED")
    
    print(f"\nProcessing {total_records:,} records with {MAX_WORKERS} workers...")
    if not TEST_STEP1_ONLY:
        print(f"   Estimated time: ~{(total_records * 50) / MAX_WORKERS / 60:.0f} minutes")
    print()
    
    all_results = []
    batch_num = 0
    
    # Process in batches for progress saving
    for batch_start in range(0, total_records, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_records)
        batch_records = records[batch_start:batch_end]
        batch_num += 1
        
        print(f"📦 Batch {batch_num}: Records {batch_start+1}-{batch_end}")
        
        batch_results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks in this batch
            futures = {
                executor.submit(process_single_record, record, batch_start + idx + 1, log_manager, test_step1_only=TEST_STEP1_ONLY): idx 
                for idx, record in enumerate(batch_records)
            }
            
            # Collect results with progress bar
            for future in tqdm(as_completed(futures), total=len(futures), 
                             desc=f"  Processing", unit="record"):
                try:
                    result = future.result()
                    batch_results.append(result)
                except Exception as e:
                    print(f"  ⚠️  Task failed: {e}")
        
        # Sort batch results by product_id
        batch_results.sort(key=lambda x: x['product_id'])
        all_results.extend(batch_results)
        
        # Save intermediate results (only if full pipeline, not Step 1 test mode)
        if not TEST_STEP1_ONLY:
            csv_file = save_results(output_dir, all_results, input_filename, log_manager)
            # Save audit files for final step
            save_audit_step_files(log_manager, all_results, "final")
        
        log_manager.log_step('run', f"Batch {batch_num} complete: {len(batch_results)} products processed")
        
        # Print batch stats
        batch_success = sum(1 for r in batch_results if r['status'] == 'success')
        batch_step1_complete = sum(1 for r in batch_results if r['status'] == 'step1_complete')
        batch_filtered = sum(1 for r in batch_results if r['status'] == 'filtered_out')
        batch_errors = sum(1 for r in batch_results if r['status'] == 'error')
        
        if TEST_STEP1_ONLY:
            print(f"  ✓ Passed Filter: {batch_step1_complete} | Filtered: {batch_filtered} | Errors: {batch_errors}")
        else:
            print(f"  ✓ Success: {batch_success} | Filtered: {batch_filtered} | Errors: {batch_errors}")
        print(f"  💾 Saved {len(all_results)} total results so far\n")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Final statistics
    print("="*80)
    print("FINAL RESULTS")
    print("="*80)
    
    # Save Step 1 filtering audit files (AFTER all batches complete)
    generate_step1_audits(log_manager, all_results)
    
    success = [r for r in all_results if r['status'] == 'success']
    filtered = [r for r in all_results if r['status'] == 'filtered_out']
    step1_complete = [r for r in all_results if r['status'] == 'step1_complete']
    errors = [r for r in all_results if r['status'] == 'error']
    
    # Initialize cost and token variables
    total_cost = 0
    total_tokens = 0
    input_tokens = 0
    output_tokens = 0
    
    print(f"\nOVERALL STATS:")
    print(f"   Total Records: {len(all_results):,}")
    
    if TEST_STEP1_ONLY:
        print(f"   ✓ Step 1 Complete (Passed Filter): {len(step1_complete):,} ({len(step1_complete)/len(all_results)*100:.1f}%)")
        print(f"   Filtered Out: {len(filtered):,} ({len(filtered)/len(all_results)*100:.1f}%)")
        print(f"   Errors: {len(errors):,} ({len(errors)/len(all_results)*100:.1f}%)")
    else:
        print(f"   ✓ Success: {len(success):,} ({len(success)/len(all_results)*100:.1f}%)")
        print(f"   Filtered: {len(filtered):,} ({len(filtered)/len(all_results)*100:.1f}%)")
        print(f"   Errors: {len(errors):,} ({len(errors)/len(all_results)*100:.1f}%)")
    
    if success:
        total_cost = sum(r['api_cost'] for r in success)
        total_tokens = sum(r['tokens_used'] for r in success)
        
        # Calculate input/output tokens separately
        input_tokens = 0
        output_tokens = 0
        for r in success:
            metadata = r.get('_metadata', {})
            tokens_breakdown = metadata.get('tokens', {})
            input_tokens += tokens_breakdown.get('prompt', 0)
            output_tokens += tokens_breakdown.get('completion', 0)
        
        avg_time = sum(r['processing_time_sec'] for r in success) / len(success)
        total_sequential = sum(r['processing_time_sec'] for r in success)
        
        print(f"\n💰 COST:")
        print(f"   Total API Cost: ${total_cost:.4f}")
        print(f"   Avg per product: ${total_cost/len(success):.6f}")
        print(f"   Total tokens: {total_tokens:,}")
        print(f"   Input tokens: {input_tokens:,}")
        print(f"   Output tokens: {output_tokens:,}")
        
        print(f"\n⏱️  TIMING:")
        print(f"   Total (parallel): {duration:.2f}s ({duration/60:.2f} min)")
        print(f"   Avg per product: {avg_time:.2f}s")
        print(f"   Sequential would be: {total_sequential/60:.2f} min")
        print(f"   ✨ Speedup: {total_sequential / duration:.1f}x")
        print(f"   Throughput: {len(all_results) / (duration/60):.1f} records/min")
    
    # Category breakdown
    if success:
        categories = {}
        hlcs = {}
        for r in success:
            cat = r.get('category', 'UNKNOWN')
            hlc = r.get('high_level_category', 'UNKNOWN')
            categories[cat] = categories.get(cat, 0) + 1
            hlcs[hlc] = hlcs.get(hlc, 0) + 1
        
        print(f"\n📦 TOP 10 CATEGORIES:")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   {cat}: {count}")
        
        print(f"\n🎯 HIGH LEVEL CATEGORIES:")
        for hlc, count in sorted(hlcs.items(), key=lambda x: x[1], reverse=True):
            print(f"   {hlc}: {count}")
    
    print(f"\n📁 OUTPUT FILES:")
    if TEST_STEP1_ONLY:
        print(f"   Step 1 Audit: {info['audit_path']}/step1_filter/")
        print(f"   Logs: {info['logs_path']}/")
        print(f"   (CSV and Final audit not generated in Step 1 test mode)")
    else:
        print(f"   CSV: {csv_file}")
        print(f"   Audit: {info['audit_path']}/final/ ({len(all_results)} files)")
        print(f"   Logs: {info['logs_path']}/")
    
    log_manager.log_step('run', f"="*80)
    log_manager.log_step('run', f"PROCESSING COMPLETE")
    log_manager.log_step('run', f"="*80)
    log_manager.log_step('run', f"Success: {len(success)}, Filtered: {len(filtered)}, Errors: {len(errors)}")
    if success:
        log_manager.log_step('run', f"Total cost: ${total_cost:.4f}")
        log_manager.log_step('run', f"Total tokens: {total_tokens:,} (input: {input_tokens:,}, output: {output_tokens:,})")
    log_manager.log_step('run', f"Total duration: {duration:.2f}s")
    if not TEST_STEP1_ONLY:
        log_manager.log_step('run', f"Output CSV: {csv_file}")
    
    # Save run manifest
    manifest_data = {
        'total_records': len(all_results),
        'success': len(success),
        'filtered': len(filtered),
        'errors': len(errors),
        'total_cost': total_cost if success else 0,
        'total_tokens': total_tokens if success else 0,
        'input_tokens': input_tokens if success else 0,
        'output_tokens': output_tokens if success else 0,
        'duration_seconds': duration,
        'test_mode_step1_only': TEST_STEP1_ONLY
    }
    if not TEST_STEP1_ONLY:
        manifest_data['output_csv'] = str(csv_file)
    log_manager.save_run_manifest(manifest_data)
    
    # Mark file as completed in tracker
    file_tracker.mark_completed(
        filename=input_filename,
        run_id=info['run_id'],
        success=len(success),
        filtered=len(filtered),
        errors=len(errors),
        total_cost=total_cost if success else 0,
        total_tokens=total_tokens if success else 0,
        input_tokens=input_tokens if success else 0,
        output_tokens=output_tokens if success else 0,
        duration_seconds=duration
    )
    
    print(f"\n" + "="*80)
    print(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total Duration: {duration:.2f}s ({duration/60:.2f} minutes)")
    print("="*80)
    print("\n✓ PRODUCTION RUN COMPLETE!")


def create_result_dict(asin: str, title: str, brand: str, 
                       category: str = 'UNKNOWN', subcategory: str = 'UNKNOWN',
                       primary_ingredient: str = '', age: str = '', gender: str = '',
                       form: str = '', organic: str = '', count: str = '', unit: str = '',
                       size: str = '', health_focus: str = '', reasoning: str = '') -> dict:
    """
    Helper function to create a standardized result dictionary
    """
    return {
        'asin': asin,
        'title': title,
        'brand': brand,
        'category': category,
        'subcategory': subcategory,
        'primary_ingredient': primary_ingredient,
        'age': age,
        'gender': gender,
        'form': form,
        'organic': organic,
        'count': count,
        'unit': unit,
        'size': size,
        'health_focus': health_focus,
        'high_level_category': assign_high_level_category(category),
        'reasoning': reasoning
    }


def apply_step2_llm(asin: str, title: str, brand: str, log_manager: LogManager, product_id: int):
    """
    Apply Step 2: LLM enrichment
    Returns: {'success': bool, 'data': dict} or {'success': False, 'error': str}
    """
    try:
        # LLM extraction
        llm_result = extract_llm_attributes(title, asin, product_id, log_manager)
        
        if not llm_result['success']:
            return {'success': False, 'error': llm_result.get('error', 'Unknown LLM error')}
        
        # Extract attributes and apply business rules
        attrs = extract_attributes_from_llm_result(llm_result['data'])
        
        # ⚠️  CHECK: If LLM returned "REMOVE" for attributes, this is a non-supplement
        # Don't process further - return a REMOVE result immediately
        age_val = attrs.get('age', '').upper()
        gender_val = attrs.get('gender', '').upper()
        form_val = attrs.get('form', '').upper()
        
        if age_val == 'REMOVE' or gender_val == 'REMOVE' or form_val == 'REMOVE':
            log_manager.log_step('step2_llm', f"[{asin}] LLM detected non-supplement (returned REMOVE for attributes)")
            return {
                'success': True,
                'data': {
                    'category': 'REMOVE',
                    'subcategory': 'REMOVE',
                    'primary_ingredient': 'REMOVE',
                    'age': 'REMOVE',
                    'gender': 'REMOVE',
                    'form': 'REMOVE',
                    'organic': 'REMOVE',
                    'count': 'REMOVE',
                    'unit': 'REMOVE',
                    'size': 'REMOVE',
                    'health_focus': 'REMOVE',
                    'high_level_category': 'REMOVE',
                    'reasoning': 'Step 2 LLM Filter: LLM detected non-supplement product (safety check)',
                    'ingredients': [],
                    'business_rules': {}
                }
            }
        
        business_rules_result = attrs.get('business_rules', {})
        
        # Return structured data
        return {
            'success': True,
            'data': {
                'category': business_rules_result.get('final_category', 'UNKNOWN'),
                'subcategory': business_rules_result.get('final_subcategory', 'UNKNOWN'),
                'primary_ingredient': business_rules_result.get('primary_ingredient', ''),
                'age': attrs.get('age', 'UNKNOWN'),
                'gender': attrs.get('gender', 'UNKNOWN'),
                'form': attrs.get('form', 'UNKNOWN'),
                'organic': attrs.get('organic', 'NOT ORGANIC'),
                'count': attrs.get('count', 'UNKNOWN'),
                'unit': attrs.get('unit', 'UNKNOWN'),
                'size': attrs.get('size', ''),
                'health_focus': business_rules_result.get('health_focus', ''),
                'high_level_category': '',  # Will be assigned later if needed
                'reasoning': business_rules_result.get('reasoning', ''),
                'ingredients': attrs.get('ingredients', []),
                'business_rules': business_rules_result
            }
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def process_llm_only(record_data):
    """
    Worker function to process a product that already passed Step 1 filter.
    Only does LLM enrichment (Step 2).
    Returns: (result_dict, error_flag)
    """
    idx, record, log_manager, db, run_id = record_data
    product_id = idx + 1
    asin = record.get('asin', f'P{product_id}')
    title = record.get('title', '')
    brand = record.get('brand', '')
    
    try:
        # Step 2: LLM Enrichment (already passed Step 1)
        step2_result = apply_step2_llm(asin, title, brand, log_manager, product_id)
        
        if step2_result['success']:
            # Check if LLM detected it as REMOVE (non-supplement)
            if step2_result['data'].get('category') == 'REMOVE':
                # Create REMOVE result with REMOVE in ALL fields
                result = create_result_dict(
                    asin=asin,
                    title=title,
                    brand=brand,
                    category='REMOVE',
                    subcategory='REMOVE',
                    primary_ingredient='REMOVE',
                    age='REMOVE',
                    gender='REMOVE',
                    form='REMOVE',
                    organic='REMOVE',
                    count='REMOVE',
                    unit='REMOVE',
                    size='REMOVE',
                    health_focus='REMOVE',
                    reasoning='Step 2 LLM Filter: LLM detected non-supplement product (safety check)'
                )
                
                # Save audit
                log_manager.save_audit_json(
                    step_name='step2_llm',
                    data={
                        'product_id': product_id,
                        'asin': asin,
                        'title': title,
                        'brand': brand,
                        'success': True,
                        'status': 'REMOVE',
                        'reason': 'LLM detected non-supplement'
                    },
                    filename=f'{asin}.json'
                )
                
                # Update DynamoDB
                db.put_record(asin=asin, run_id=run_id, status='filtered', data={'reason': 'LLM detected non-supplement'})
                
                return (result, False)
            
            # Success - create full result
            result = create_result_dict(
                asin=asin,
                title=title,
                brand=brand,
                category=step2_result['data'].get('category', ''),
                subcategory=step2_result['data'].get('subcategory', ''),
                primary_ingredient=step2_result['data'].get('primary_ingredient', ''),
                age=step2_result['data'].get('age', ''),
                gender=step2_result['data'].get('gender', ''),
                form=step2_result['data'].get('form', ''),
                organic=step2_result['data'].get('organic', ''),
                count=step2_result['data'].get('count', ''),
                unit=step2_result['data'].get('unit', ''),
                size=step2_result['data'].get('size', ''),
                health_focus=step2_result['data'].get('health_focus', ''),
                reasoning=step2_result['data'].get('reasoning', '')
            )
            
            # Save audit
            log_manager.save_audit_json(
                step_name='step2_llm',
                data={
                    'product_id': product_id,
                    'asin': asin,
                    'title': title,
                    'brand': brand,
                    'success': True,
                    'result': step2_result['data']
                },
                filename=f'{asin}.json'
            )
            
            # Update DynamoDB
            db.put_record(asin=asin, run_id=run_id, status='success', data=result)
            
            return (result, False)
        else:
            # LLM Error - create error result
            error_result = create_result_dict(
                asin=asin,
                title=title,
                brand=brand,
                category='ERROR',
                subcategory='ERROR',
                reasoning=f"LLM Error: {step2_result['error']}"
            )
            
            # Save error audit
            log_manager.save_audit_json(
                step_name='step2_llm',
                data={
                    'product_id': product_id,
                    'asin': asin,
                    'title': title,
                    'brand': brand,
                    'success': False,
                    'error': step2_result['error']
                },
                filename=f'{asin}.json'
            )
            
            # Update DynamoDB
            db.put_record(asin=asin, run_id=run_id, status='error', data={'error': step2_result['error']})
            
            return (error_result, True)
            
    except Exception as e:
        # Unexpected error
        error_result = create_result_dict(
            asin=asin,
            title=title,
            brand=brand,
            category='ERROR',
            subcategory='ERROR',
            reasoning=f"Processing Error: {str(e)}"
        )
        
        log_manager.save_audit_json(
            step_name='step2_llm',
            data={
                'product_id': product_id,
                'asin': asin,
                'error': str(e)
            },
            filename=f'{asin}.json'
        )
        
        db.put_record(asin=asin, run_id=run_id, status='error', data={'error': str(e)})
        
        return (error_result, True)


def process_single_product(record_data):
    """
    Worker function to process a single product
    Returns: (result_dict or None, filtered_count, error_info)
    """
    idx, record, log_manager, db, run_id = record_data
    product_id = idx + 1
    asin = record.get('asin', f'P{product_id}')
    title = record.get('title', '')
    
    try:
        # Step 1: Filter
        step1_result = apply_step1_filter(
            title,
            record.get('amazon_subcategory', '').lower().strip(),
            asin,
            log_manager
        )
        
        if not step1_result['passed']:
            # Filtered - create result with REMOVE in ALL fields
            # ⚠️  User requirement: ALL fields should say "REMOVE" for filtered items
            filter_type = step1_result.get('filter_type', 'unknown')
            filter_reason = step1_result.get('filter_reason', 'Non-supplement')
            
            # Create detailed reasoning
            if filter_type == 'filtered_by_remove':
                detailed_reason = f"Step 1 Filter: Amazon subcategory marked as REMOVE - {filter_reason}"
            elif filter_type == 'filtered_by_keyword':
                detailed_reason = f"Step 1 Filter: {filter_reason}"
            else:
                detailed_reason = f"Step 1 Filter: {filter_reason}"
            
            filter_result = create_result_dict(
                asin=asin,
                title=title,
                brand=record.get('brand', ''),
                category='REMOVE',
                subcategory='REMOVE',
                primary_ingredient='REMOVE',
                age='REMOVE',
                gender='REMOVE',
                form='REMOVE',
                organic='REMOVE',
                count='REMOVE',
                unit='REMOVE',
                size='REMOVE',
                health_focus='REMOVE',
                reasoning=detailed_reason
            )
            
            # Save audit
            audit_filter = {
                'asin': asin,
                'title': title,
                'status': 'REMOVE',
                'filter_reason': step1_result['filter_reason'],
                'step_completed': 1
            }
            log_manager.save_audit_json('step1_filter', audit_filter, f"{asin}.json")
            
            db.put_record(
                asin=asin,
                run_id=run_id,
                status='filtered',
                data={'reason': step1_result['filter_reason']}
            )
            return (filter_result, 1, None)  # Return result for CSV, count as filtered
        
        # Step 2: LLM extraction
        llm_result = extract_llm_attributes(title, asin, product_id, log_manager)
        
        if not llm_result['success']:
            # Error - create error result for CSV
            error_msg = llm_result.get('error', 'Unknown error')
            error_result = create_result_dict(
                asin=asin,
                title=title,
                brand=record.get('brand', ''),
                category='ERROR',
                subcategory='ERROR',
                reasoning=f"LLM Error: {error_msg}"
            )
            
            db.put_record(
                asin=asin,
                run_id=run_id,
                status='error',
                data={'error': error_msg}
            )
            
            log_manager.save_audit_json('errors', {
                'asin': asin,
                'title': title,
                'status': 'ERROR',
                'error': error_msg,
                'step_completed': 2
            }, f"{asin}.json")
            
            return (error_result, 0, error_msg)  # Return error result for CSV
        
        # Extract attributes
        attrs = extract_attributes_from_llm_result(llm_result['data'])
        
        # ⚠️  CHECK: If LLM returned "REMOVE" for attributes, this is a non-supplement
        # Don't process further - return a REMOVE result immediately
        age_val = attrs.get('age', '').upper()
        gender_val = attrs.get('gender', '').upper()
        form_val = attrs.get('form', '').upper()
        
        if age_val == 'REMOVE' or gender_val == 'REMOVE' or form_val == 'REMOVE':
            log_manager.log_step('step2_llm', f"[{asin}] LLM detected non-supplement (returned REMOVE for attributes)")
            
            # Create REMOVE result with REMOVE in ALL fields
            result = create_result_dict(
                asin=asin,
                title=title,
                brand=record.get('brand', ''),
                category='REMOVE',
                subcategory='REMOVE',
                primary_ingredient='REMOVE',
                age='REMOVE',
                gender='REMOVE',
                form='REMOVE',
                organic='REMOVE',
                count='REMOVE',
                unit='REMOVE',
                size='REMOVE',
                health_focus='REMOVE',
                reasoning='Step 2 LLM Filter: LLM detected non-supplement product (safety check)'
            )
            
            # Save audit
            audit_filter = {
                'asin': asin,
                'title': title,
                'status': 'REMOVE',
                'filter_reason': 'LLM detected non-supplement product',
                'step_completed': 2
            }
            log_manager.save_audit_json('step2_llm', audit_filter, f"{asin}.json")
            
            db.put_record(
                asin=asin,
                run_id=run_id,
                status='filtered',
                data={'reason': 'LLM detected non-supplement'}
            )
            return (result, 1, None)  # Return result for CSV, count as filtered
        
        business_rules_result = attrs.get('business_rules', {})
        
        # Build result using helper
        result = create_result_dict(
            asin=asin,
            title=title,
            brand=record.get('brand', ''),
            category=business_rules_result.get('final_category', 'UNKNOWN'),
            subcategory=business_rules_result.get('final_subcategory', 'UNKNOWN'),
            primary_ingredient=business_rules_result.get('primary_ingredient', ''),
            age=attrs.get('age', 'UNKNOWN'),
            gender=attrs.get('gender', 'UNKNOWN'),
            form=attrs.get('form', 'UNKNOWN'),
            organic=attrs.get('organic', 'NOT ORGANIC'),
            count=attrs.get('count', 'UNKNOWN'),
            unit=attrs.get('unit', 'UNKNOWN'),
            size=attrs.get('size', ''),
            health_focus=business_rules_result.get('health_focus', ''),
            reasoning=business_rules_result.get('reasoning', '')
        )
        
        # Save audit JSON with full processing details
        audit_result = result.copy()
        audit_result.update({
            'status': 'SUCCESS',
            'step_completed': 3,
            'ingredients': attrs.get('ingredients', []),
            'business_rules': business_rules_result
        })
        log_manager.save_audit_json('step3_postprocess', audit_result, f"{asin}.json")
        
        # Write success to DynamoDB
        db.put_record(
            asin=asin,
            run_id=run_id,
            status='success',
            data=result
        )
        
        return (result, 0, None)  # result, 0 filtered, no error
        
    except Exception as e:
        error_msg = str(e)
        
        # Create error result for CSV
        error_result = create_result_dict(
            asin=asin,
            title=title,
            brand=record.get('brand', ''),
            category='ERROR',
            subcategory='ERROR',
            reasoning=f"Processing Error: {error_msg}"
        )
        
        # Save audit
        error_audit = {
            'asin': asin,
            'title': title,
            'status': 'ERROR',
            'error': error_msg,
            'step_completed': 0
        }
        log_manager.save_audit_json('errors', error_audit, f"{asin}.json")
        
        db.put_record(
            asin=asin,
            run_id=run_id,
            status='error',
            data={'error': error_msg}
        )
        return (error_result, 0, error_msg)  # Return error result for CSV


def process_aws_mode(
    s3_bucket: str,
    input_key: str,
    output_prefix: str,
    audit_prefix: str,
    logs_prefix: str,
    dynamodb_table: str,
    sns_topic_arn: str = None
):
    """
    AWS Cloud Processing Mode
    Reads from S3, processes, writes to S3, tracks in DynamoDB
    Uses single S3 bucket with folder prefixes
    Structure: {prefix}{filename}/run_1/, run_2/, etc.
    """
    if not AWS_AVAILABLE:
        print("⚠ AWS mode requires boto3 and AWS modules")
        sys.exit(1)
    
    start_time = datetime.now()
    
    # Extract filename without extension
    input_filename = Path(input_key).stem
    
    # ✓ VALIDATE: File must start with "uncoded_"
    if not input_filename.lower().startswith('uncoded_'):
        error_msg = f"⚠ ERROR: Input file must start with 'uncoded_'. Got: {input_filename}"
        print(error_msg)
        if sns_topic_arn:
            send_invalid_filename_notification(sns_topic_arn, input_filename)
        raise ValueError(f"Invalid filename: {input_filename}. Must start with 'uncoded_'")
    
    # Create clean filename for output: remove "uncoded_" prefix
    # Example: uncoded_100_records -> 100_records
    file_id = input_filename[8:] if input_filename.lower().startswith('uncoded_') else input_filename
    
    # Get next run number by checking existing runs in S3
    s3 = S3Manager()
    s3_client = boto3.client('s3')
    
    run_number = 1
    try:
        # List existing runs for this file (use file_id without uncoded_ prefix)
        prefix = f"{output_prefix}{file_id}/"
        response = s3_client.list_objects_v2(Bucket=s3_bucket, Prefix=prefix, Delimiter='/')
        
        if 'CommonPrefixes' in response:
            # Extract run numbers
            existing_runs = []
            for item in response['CommonPrefixes']:
                folder = item['Prefix'].rstrip('/').split('/')[-1]
                if folder.startswith('run_'):
                    try:
                        num = int(folder.split('_')[1])
                        existing_runs.append(num)
                    except:
                        pass
            
            if existing_runs:
                run_number = max(existing_runs) + 1
    except Exception as e:
        print(f"⚠️  Could not determine run number, using run_1: {e}")
    
    run_folder = f"run_{run_number}"
    
    print("="*80)
    print("AWS CLOUD PROCESSING - Bedrock AI Data Enrichment")
    print("="*80)
    print(f"\nFile: {input_filename} (output as: {file_id}_coded.csv)")
    print(f"Run: {run_folder}")
    print(f"S3 Bucket: s3://{s3_bucket}/")
    print(f"Input: s3://{s3_bucket}/{input_key}")
    print(f"Output: s3://{s3_bucket}/{output_prefix}{file_id}/{run_folder}/")
    print(f"Audit: s3://{s3_bucket}/{audit_prefix}{file_id}/{run_folder}/")
    print(f"Logs: s3://{s3_bucket}/{logs_prefix}{file_id}/{run_folder}/")
    
    try:
        # Initialize AWS managers (reuse s3 from above)
        db = DynamoDBManager(dynamodb_table)
        
        # Read input CSV from S3
        print(f"\nReading input data...")
        df = s3.read_csv_from_s3(s3_bucket, input_key, encoding='latin-1')
        
        if df is None:
            print("⚠ Failed to read input file")
            return
        
        # Standardize
        df = standardize_dataframe(df)
        total_records = len(df)
        print(f"✓ Loaded {total_records:,} records")
        
        # Create log manager (will write to local /tmp then upload to S3)
        log_manager = LogManager(
            input_filename=input_filename,
            base_path='/tmp/bedrock-data'
        )
        
        # Send "Processing Started" notification
        if sns_topic_arn:
            send_processing_started_notification(
                sns_topic_arn=sns_topic_arn,
                input_key=input_key,
                input_filename=input_filename,
                run_folder=run_folder,
                total_records=total_records,
                s3_bucket=s3_bucket
            )
        
        print(f"\nSTEP 1: Fast filtering all {total_records:,} records...")
        
        results = []
        filtered_count = 0
        error_count = 0
        llm_needed_tasks = []  # Products that need LLM processing
        
        # STEP 1: Filter ALL records first (fast, no API calls)
        for idx, record in df.iterrows():
            product_id = idx + 1
            asin = record.get('asin', f'P{product_id}')
            title = record.get('title', '')
            brand = record.get('brand', '')
            
            # Apply Step 1 filter
            step1_result = apply_step1_filter(
                title,
                record.get('amazon_subcategory', '').lower().strip(),
                asin,
                log_manager
            )
            
            if not step1_result['passed']:
                # Filtered - add to results immediately with ALL fields as REMOVE
                filter_type = step1_result.get('filter_type', 'unknown')
                filter_reason = step1_result.get('filter_reason', 'Non-supplement')
                
                # Create detailed reasoning
                if filter_type == 'filtered_by_remove':
                    detailed_reason = f"Step 1 Filter: Amazon subcategory marked as REMOVE - {filter_reason}"
                elif filter_type == 'filtered_by_keyword':
                    detailed_reason = f"Step 1 Filter: {filter_reason}"
                else:
                    detailed_reason = f"Step 1 Filter: {filter_reason}"
                
                filter_result = create_result_dict(
                    asin=asin,
                    title=title,
                    brand=brand,
                    category='REMOVE',
                    subcategory='REMOVE',
                    primary_ingredient='REMOVE',
                    age='REMOVE',
                    gender='REMOVE',
                    form='REMOVE',
                    organic='REMOVE',
                    count='REMOVE',
                    unit='REMOVE',
                    size='REMOVE',
                    health_focus='REMOVE',
                    reasoning=detailed_reason
                )
                results.append(filter_result)
                filtered_count += 1
                
                # Save audit for filtered product
                log_manager.save_audit_json(
                    step_name='step1_filter',
                    data={
                        'product_id': product_id,
                        'asin': asin,
                        'title': title,
                        'passed': False,
                        'filter_reason': step1_result['filter_reason']
                    },
                    filename=f'{asin}.json'
                )
            else:
                # Passed filter - queue for LLM processing
                llm_needed_tasks.append((idx, record, log_manager, db, run_folder))
        
        llm_count = len(llm_needed_tasks)
        print(f"✓ Step 1 complete: {filtered_count:,} filtered, {llm_count:,} need LLM enrichment")
        
        # STEP 2: Process LLM-needed products with 200 parallel workers
        if llm_count > 0:
            print(f"\nSTEP 2: LLM enrichment for {llm_count:,} products with 200 parallel workers...")
            
            # Track overall processing status in DynamoDB
            processing_key = f"{input_filename}_processing"
            db.put_record(
                asin=processing_key,
                run_id=run_folder,
                status='in_progress',
                data={
                    'total': total_records,
                    'filtered': filtered_count,
                    'llm_needed': llm_count,
                    'processed': 0,
                    'errors': 0,
                    'start_time': start_time.isoformat()
                }
            )
            
            processed_count = 0
            with ThreadPoolExecutor(max_workers=200) as executor:
                futures = {executor.submit(process_llm_only, task): task[0] for task in llm_needed_tasks}
                
                # Progress bar
                with tqdm(total=llm_count, desc="LLM Processing", unit="product") as pbar:
                    for future in as_completed(futures):
                        result, error = future.result()
                        
                        if result:
                            results.append(result)
                        if error:
                            error_count += 1
                        
                        processed_count += 1
                        pbar.update(1)
                        
                        # Update DynamoDB heartbeat every 100 products
                        if processed_count % 100 == 0:
                            db.put_record(
                                asin=processing_key,
                                run_id=run_folder,
                                status='in_progress',
                                data={
                                    'total': total_records,
                                    'filtered': filtered_count,
                                    'llm_needed': llm_count,
                                    'llm_processed': processed_count,
                                    'enriched': processed_count - error_count,
                                    'errors': error_count,
                                    'progress_pct': round((processed_count / llm_count) * 100, 1),
                                    'last_update': datetime.now().isoformat()
                                }
                            )
        else:
            print(f"\n✓ All products filtered - no LLM calls needed!")
        
        # Final status update
        db.put_record(
            asin=processing_key,
            run_id=run_folder,
            status='completed',
            data={
                'total': total_records,
                'processed': processed_count,
                'enriched': len(results),
                'filtered': filtered_count,
                'errors': error_count,
                'progress_pct': 100.0,
                'end_time': datetime.now().isoformat()
            }
        )
        
        # Convert results to DataFrame
        if results:
            results_df = pd.DataFrame(results)
            
            # Write to S3 (output folder with file/run_N structure)
            # Output filename: {file_id}_coded.csv (e.g., 100_records_coded.csv)
            output_key = f"{output_prefix}{file_id}/{run_folder}/{file_id}_coded.csv"
            s3.write_csv_to_s3(results_df, s3_bucket, output_key)
            
            print(f"\n✓ Processing complete!")
            print(f"   Processed: {len(results)} products")
            print(f"   Output: s3://{s3_bucket}/{output_key}")
        
        # Upload audit files to S3 (audit folder with file/run_N structure)
        audit_s3_prefix = f"{audit_prefix}{file_id}/{run_folder}/audit"
        audit_dir = Path(f'/tmp/bedrock-data/audit/{input_filename}')
        print(f"\n   Checking audit directory: {audit_dir}")
        print(f"   Exists: {audit_dir.exists()}")
        if audit_dir.exists():
            file_count = len(list(audit_dir.rglob('*.*')))
            print(f"   Found {file_count} files in audit directory")
            count = s3.upload_directory(audit_dir, s3_bucket, audit_s3_prefix)
            print(f"   ✓ Uploaded {count} audit files to S3")
        else:
            print(f"   ⚠ Audit directory does not exist")
        
        # Upload logs to S3 (logs folder with file/run_N structure)
        logs_s3_prefix = f"{logs_prefix}{file_id}/{run_folder}/logs"
        logs_dir = Path(f'/tmp/bedrock-data/logs/{input_filename}')
        print(f"\n   Checking logs directory: {logs_dir}")
        print(f"   Exists: {logs_dir.exists()}")
        if logs_dir.exists():
            file_count = len(list(logs_dir.rglob('*.*')))
            print(f"   Found {file_count} files in logs directory")
            count = s3.upload_directory(logs_dir, s3_bucket, logs_s3_prefix)
            print(f"   ✓ Uploaded {count} log files to S3")
        else:
            print(f"   ⚠ Logs directory does not exist")
        
        # Send success notification
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds() / 60
        
        if sns_topic_arn:
            send_success_notification(
                sns_topic_arn=sns_topic_arn,
                input_key=input_key,
                input_filename=input_filename,
                run_folder=run_folder,
                total_records=total_records,
                enriched_count=len(results) - filtered_count - error_count,  # Only LLM enriched
                filtered_count=filtered_count,
                error_count=error_count,
                duration_minutes=duration,
                s3_bucket=s3_bucket,
                output_prefix=output_prefix,
                audit_prefix=audit_prefix,
                logs_prefix=logs_prefix
            )
    
    except Exception as e:
        # Send error notification
        if sns_topic_arn:
            send_error_notification(sns_topic_arn, input_key, run_folder if 'run_folder' in locals() else None, str(e))
        raise


if __name__ == '__main__':
    import sys
    import traceback
    
    # Force stdout/stderr to flush immediately for Docker/CloudWatch
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    
    print("="*80)
    print("BEDROCK AI DATA ENRICHMENT - STARTING")
    print("="*80)
    
    try:
        parser = argparse.ArgumentParser(description='Bedrock AI Data Enrichment Pipeline')
        parser.add_argument('--mode', choices=['local', 'aws'], default='local',
                           help='Execution mode: local (default) or aws (cloud)')
        parser.add_argument('input_file', nargs='?', default=None,
                           help='Input CSV file path (local mode)')
        
        # AWS mode arguments
        parser.add_argument('--input-key', help='S3 input key (AWS mode)')
        
        args = parser.parse_args()
        
        if args.mode == 'aws':
            # AWS mode - use env vars (set by ECS task)
            S3_BUCKET = os.getenv('S3_BUCKET')
            INPUT_KEY = args.input_key or os.getenv('INPUT_KEY')
            OUTPUT_PREFIX = os.getenv('OUTPUT_PREFIX', 'output/')
            AUDIT_PREFIX = os.getenv('AUDIT_PREFIX', 'audit/')
            LOGS_PREFIX = os.getenv('LOGS_PREFIX', 'logs/')
            DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE')
            SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')
            
            if not S3_BUCKET or not INPUT_KEY:
                print("ERROR: S3_BUCKET and INPUT_KEY are required for AWS mode")
                sys.exit(1)
            
            process_aws_mode(
                s3_bucket=S3_BUCKET,
                input_key=INPUT_KEY,
                output_prefix=OUTPUT_PREFIX,
                audit_prefix=AUDIT_PREFIX,
                logs_prefix=LOGS_PREFIX,
                dynamodb_table=DYNAMODB_TABLE,
                sns_topic_arn=SNS_TOPIC_ARN
            )
        else:
            # Local mode - existing behavior
            # Override INPUT_FILE if provided via command line
            if args.input_file:
                # Temporarily set sys.argv for main() to read
                original_argv = sys.argv
                sys.argv = ['main.py', args.input_file]
                main()
                sys.argv = original_argv
            else:
                main()
    
    except Exception as e:
        # Emergency error logging - catches ANY error including startup failures
        error_msg = f"CRITICAL ERROR: {str(e)}"
        error_trace = traceback.format_exc()
        
        print("=" * 80)
        print("CRITICAL ERROR CAUGHT AT TOP LEVEL")
        print("=" * 80)
        print(error_msg)
        print("")
        print("Full traceback:")
        print(error_trace)
        print("=" * 80)
        
        # Try to send SNS notification if possible
        try:
            if args.mode == 'aws':
                SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')
                INPUT_KEY = args.input_key or os.getenv('INPUT_KEY', 'unknown')
                if SNS_TOPIC_ARN and AWS_AVAILABLE:
                    import boto3
                    sns = boto3.client('sns')
                    sns.publish(
                        TopicArn=SNS_TOPIC_ARN,
                        Subject=f"CRITICAL: Startup Failure - {INPUT_KEY}",
                        Message=f"Critical error during startup:\n\n{error_msg}\n\nTraceback:\n{error_trace}"
                    )
                    print("Emergency notification sent to SNS")
        except Exception as notification_error:
            print(f"Could not send emergency notification: {notification_error}")
        
        sys.exit(2)

