"""
Step 1: Non-Supplement Filtering

Two-phase filtering:
1. Check amazon_subcategory_lookup for REMOVE/REMAP/UNKNOWN
2. For REMAP and UNKNOWN, apply keyword safety net
"""

import pandas as pd
import time
from typing import List, Dict, Tuple, Any
from pathlib import Path
from datetime import datetime
from src.core.log_manager import LogManager
from src.utils.preprocessing import is_non_supplement


# Global cache for lookup table
_LOOKUP_DF = None


def load_amazon_subcategory_lookup() -> pd.DataFrame:
    """Load amazon subcategory lookup table (cached)"""
    global _LOOKUP_DF
    
    if _LOOKUP_DF is not None:
        return _LOOKUP_DF
    
    lookup_path = Path('reference_data/amazon_subcategory_lookup.csv')
    if not lookup_path.exists():
        _LOOKUP_DF = pd.DataFrame()
        return _LOOKUP_DF
    
    df = pd.read_csv(lookup_path)
    # Normalize column names
    df.columns = df.columns.str.lower().str.strip()
    # Convert amazon_subcategory to lowercase for matching
    if 'amazon_subcategory' in df.columns:
        df['amazon_subcategory'] = df['amazon_subcategory'].str.lower().str.strip()
    
    _LOOKUP_DF = df
    return _LOOKUP_DF


def get_subcategory_action(amazon_subcat: str) -> Tuple[str, str, str, str]:
    """
    Look up amazon subcategory and return action + details
    
    Returns:
        Tuple of (action, nw_category, nw_subcategory, notes)
        action can be: 'REMOVE', 'REMAP', or 'UNKNOWN'
    """
    if not amazon_subcat or amazon_subcat == 'nan':
        return ('UNKNOWN', '', '', 'No amazon_subcategory provided')
    
    lookup_df = load_amazon_subcategory_lookup()
    
    if lookup_df.empty:
        return ('UNKNOWN', '', '', 'Lookup table not found')
    
    match = lookup_df[lookup_df['amazon_subcategory'] == amazon_subcat]
    
    if match.empty:
        return ('UNKNOWN', '', '', 'Amazon subcategory not found in lookup table')
    
    action = match.iloc[0].get('action', '').upper()
    nw_category = match.iloc[0].get('nw_category', '')
    nw_subcategory = match.iloc[0].get('nw_subcategory', '')
    notes = match.iloc[0].get('notes', '')
    
    return (action, nw_category, nw_subcategory, notes)


def apply_step1_filter(
    title: str,
    amazon_subcat: str,
    asin: str,
    log_manager: LogManager
) -> Dict[str, Any]:
    """
    Apply Step 1 filtering logic
    
    Returns:
        Dict with:
        - 'passed': bool - True if passed filtering
        - 'action': str - REMOVE, REMAP, or UNKNOWN
        - 'filter_type': str - 'filtered_by_remove' or 'filtered_by_keyword' if filtered
        - 'filter_reason': str - Reason for filtering
        - 'nw_category': str - For REMAP actions
        - 'nw_subcategory': str - For REMAP actions
        - 'remap_reason': str - For REMAP actions
    """
    
    log_manager.log_step('step1_filter', f"[{asin}] Checking: {title[:80]}...")
    
    # Look up amazon subcategory
    action, nw_category, nw_subcategory, notes = get_subcategory_action(amazon_subcat)
    
    # Decision tree based on lookup action
    if action == 'REMOVE':
        # Immediately filter - no keyword check needed
        log_manager.log_step('step1_filter', f"[{asin}] FILTERED OUT: Amazon subcategory marked as REMOVE")
        return {
            'passed': False,
            'action': 'REMOVE',
            'filter_type': 'filtered_by_remove',
            'filter_reason': notes
        }
    
    elif action == 'REMAP' or action == 'UNKNOWN':
        # Check title for non-supplement keywords (safety net)
        is_non_supp, keyword_reason = is_non_supplement(title)
        
        if is_non_supp:
            log_manager.log_step('step1_filter', f"[{asin}] FILTERED OUT: {keyword_reason}")
            return {
                'passed': False,
                'action': action,
                'filter_type': 'filtered_by_keyword',
                'filter_reason': keyword_reason
            }
        
        # Passed keyword check
        if action == 'REMAP':
            log_manager.log_step('step1_filter', f"[{asin}] PASSED - REMAP: {nw_category}/{nw_subcategory}")
            return {
                'passed': True,
                'action': 'REMAP',
                'nw_category': nw_category,
                'nw_subcategory': nw_subcategory,
                'remap_reason': notes
            }
        else:  # UNKNOWN
            log_manager.log_step('step1_filter', f"[{asin}] PASSED - UNKNOWN subcategory")
            return {
                'passed': True,
                'action': 'UNKNOWN'
            }
    
    # Should never reach here
    log_manager.log_step('step1_filter', f"[{asin}] PASSED filtering")
    return {'passed': True, 'action': 'UNKNOWN'}


def generate_step1_audits(log_manager: LogManager, all_results: List[Dict]):
    """
    Generate Step 1 filtering audit CSV files + statistics JSON
    
    Creates:
    1. records_filtered_by_remove.csv - Products filtered by REMOVE action
    2. records_filtered_by_keyword.csv - Products filtered by keyword matching (from REMAP or UNKNOWN)
    3. records_remap.csv - Products needing category REMAP (passed keyword check)
    4. records_unknown.csv - Products with unknown subcategory (passed keyword check)
    5. step1_statistics.json - Detailed statistics with breakdowns
    """
    
    start_time = time.time()
    total_records = len(all_results)
    
    # Separate results by status
    filtered_by_remove = [r for r in all_results if r['status'] == 'filtered_by_remove']
    filtered_by_keyword = [r for r in all_results if r['status'] == 'filtered_by_keyword']
    passed = [r for r in all_results if r['status'] in ['success', 'step1_complete', 'error']]
    
    # FILE 1: records_filtered_by_remove.csv
    remove_records = []
    for r in filtered_by_remove:
        remove_records.append({
            'asin': r.get('asin', ''),
            'title': r.get('title', ''),
            'brand': r.get('brand', ''),
            'amazon_subcategory': r.get('source_subcategory', ''),
            'action': 'REMOVE',
            'reason': r.get('filter_reason', '')
        })
    
    if remove_records:
        df_remove = pd.DataFrame(remove_records)
        log_manager.save_audit_csv('step1_filter', df_remove, 'records_filtered_by_remove.csv')
    
    # FILE 2: records_filtered_by_keyword.csv
    keyword_records = []
    for r in filtered_by_keyword:
        reason = r.get('filter_reason', '')
        keyword = reason.replace('Contains non-supplement keyword: ', '').strip().strip("'\"")
        lookup_action = r.get('lookup_action', 'UNKNOWN')
        
        keyword_records.append({
            'asin': r.get('asin', ''),
            'title': r.get('title', ''),
            'brand': r.get('brand', ''),
            'amazon_subcategory': r.get('source_subcategory', ''),
            'lookup_action': lookup_action,
            'filter_reason': reason,
            'matched_keyword': keyword
        })
    
    if keyword_records:
        df_keyword = pd.DataFrame(keyword_records)
        log_manager.save_audit_csv('step1_filter', df_keyword, 'records_filtered_by_keyword.csv')
    
    # FILE 3 & 4: Process PASSED products for REMAP and UNKNOWN
    remap_records = []
    unknown_records = []
    
    for r in passed:
        lookup_action = r.get('lookup_action', 'UNKNOWN')
        amazon_subcat = r.get('source_subcategory', '')
        
        if lookup_action == 'REMAP':
            remap_records.append({
                'asin': r.get('asin', ''),
                'title': r.get('title', ''),
                'brand': r.get('brand', ''),
                'amazon_subcategory': amazon_subcat,
                'action': 'REMAP',
                'nw_category': r.get('nw_category', ''),
                'nw_subcategory': r.get('nw_subcategory', ''),
                'remap_reason': r.get('remap_reason', '')
            })
        elif lookup_action == 'UNKNOWN':
            unknown_records.append({
            'asin': r.get('asin', ''),
            'title': r.get('title', ''),
            'brand': r.get('brand', ''),
                'amazon_subcategory': amazon_subcat,
                'reason': 'Amazon subcategory not found in lookup table'
            })
    
    if remap_records:
        df_remap = pd.DataFrame(remap_records)
        log_manager.save_audit_csv('step1_filter', df_remap, 'records_remap.csv')
    
    if unknown_records:
        df_unknown = pd.DataFrame(unknown_records)
        log_manager.save_audit_csv('step1_filter', df_unknown, 'records_unknown.csv')
    
    # FILE 5: step1_statistics.json - Detailed statistics
    
    # Calculate percentages
    def calc_pct(count):
        return round((count / total_records * 100), 2) if total_records > 0 else 0
    
    # Count unknown subcategories
    unknown_subcats = {}
    for rec in unknown_records:
        subcat = rec.get('amazon_subcategory', 'N/A')
        unknown_subcats[subcat] = unknown_subcats.get(subcat, 0) + 1
    
    # Count keywords
    keyword_counts = {}
    for rec in keyword_records:
        keyword = rec.get('matched_keyword', 'unknown')
        keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
    
    # Count removed subcategories
    removed_subcats = {}
    for rec in remove_records:
        subcat = rec.get('amazon_subcategory', 'N/A')
        removed_subcats[subcat] = removed_subcats.get(subcat, 0) + 1
    
    # Count remap subcategories
    remap_subcats = {}
    for rec in remap_records:
        subcat = rec.get('amazon_subcategory', 'N/A')
        remap_subcats[subcat] = remap_subcats.get(subcat, 0) + 1
    
    # Sort and get top 10
    top_removed = dict(sorted(removed_subcats.items(), key=lambda x: x[1], reverse=True)[:10])
    top_remap = dict(sorted(remap_subcats.items(), key=lambda x: x[1], reverse=True)[:10])
    keyword_breakdown = dict(sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True))
    
    # Build statistics JSON
    info = log_manager.get_info()
    statistics = {
        "run_info": {
            "file_id": info['file_id'],
            "run_id": info['run_id'],
            "run_num": info['run_num'],
            "generated_at": datetime.utcnow().isoformat(),
            "total_records_checked": total_records,
            "processing_duration_seconds": round(time.time() - start_time, 2)
        },
        
        "filtering_summary": {
            "filtered_by_remove": {
                "count": len(remove_records),
                "percentage": calc_pct(len(remove_records))
            },
            "filtered_by_keyword": {
                "count": len(keyword_records),
                "percentage": calc_pct(len(keyword_records))
            },
            "marked_for_remap": {
                "count": len(remap_records),
                "percentage": calc_pct(len(remap_records))
            },
            "unknown_subcategory": {
                "count": len(unknown_records),
                "percentage": calc_pct(len(unknown_records))
            },
            "total_removed": {
                "count": len(remove_records) + len(keyword_records),
                "percentage": calc_pct(len(remove_records) + len(keyword_records))
            },
            "total_to_llm": {
                "count": len(remap_records) + len(unknown_records),
                "percentage": calc_pct(len(remap_records) + len(unknown_records))
            }
        },
        
        "unknown_subcategories": unknown_subcats,
        
        "keyword_breakdown": keyword_breakdown,
        
        "top_removed_subcategories": top_removed,
        
        "top_remap_subcategories": top_remap
    }
    
    # Save statistics JSON
    log_manager.save_audit_json('step1_filter', statistics, 'step1_statistics.json')
    
    # Statistics in log (keep existing logging)
    log_manager.log_step('step1_filter', "=" * 60)
    log_manager.log_step('step1_filter', "STEP 1 FILTERING STATISTICS")
    log_manager.log_step('step1_filter', "=" * 60)
    log_manager.log_step('step1_filter', f"Total products checked: {total_records}")
    log_manager.log_step('step1_filter', f"")
    log_manager.log_step('step1_filter', f"FILTERED BY REMOVE ACTION: {len(remove_records)}")
    log_manager.log_step('step1_filter', f"FILTERED BY KEYWORD: {len(keyword_records)}")
    log_manager.log_step('step1_filter', f"MARKED FOR REMAP: {len(remap_records)}")
    log_manager.log_step('step1_filter', f"UNKNOWN SUBCATEGORY: {len(unknown_records)}")
    log_manager.log_step('step1_filter', f"")
    log_manager.log_step('step1_filter', f"Total to be removed: {len(remove_records) + len(keyword_records)}")
    log_manager.log_step('step1_filter', f"Total to proceed to LLM: {len(remap_records) + len(unknown_records)}")
    log_manager.log_step('step1_filter', "=" * 60)
