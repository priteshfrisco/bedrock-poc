#!/usr/bin/env python3
"""
Cost Analysis Script - Extracts cost/token data from audit files and updates tracking
Usage: 
    Local (audit files): python analyze_costs.py --file-id 100_records --run-id run_9
    Local (update JSON): python analyze_costs.py --file-id 100_records --run-id run_9 --update-tracker
    S3 (with DynamoDB): python analyze_costs.py --s3 --bucket BUCKET --file-id 100_records --run-id run_1 --update-db
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from decimal import Decimal
from datetime import datetime

try:
    import boto3
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False
    print("⚠ boto3 not available - S3/DynamoDB operations disabled")


def load_audit_files_local(base_path: str, file_id: str, run_id: str) -> List[Dict]:
    """Load all audit JSON files from local filesystem"""
    audit_path = Path(base_path) / 'audit' / file_id / run_id
    
    results = []
    
    # Check all subdirectories for JSON files
    for subdir in ['step2_llm', 'step3_postprocess', 'final', 'errors']:
        subdir_path = audit_path / subdir
        if subdir_path.exists():
            for json_file in subdir_path.glob('*.json'):
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        results.append(data)
                except Exception as e:
                    print(f"⚠ Error loading {json_file}: {e}")
    
    return results


def load_audit_files_s3(bucket: str, file_id: str, run_id: str, audit_prefix: str = 'audit/') -> List[Dict]:
    """Load all audit JSON files from S3"""
    if not AWS_AVAILABLE:
        print("⚠ Error: boto3 not available for S3 operations")
        return []
    
    s3_client = boto3.client('s3')
    
    results = []
    prefix = f"{audit_prefix}{file_id}/{run_id}/"
    
    print(f"📁 Reading audit files from s3://{bucket}/{prefix}")
    
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        
        json_count = 0
        for page in pages:
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                key = obj['Key']
                if key.endswith('.json'):
                    json_count += 1
                    try:
                        response = s3_client.get_object(Bucket=bucket, Key=key)
                        data = json.loads(response['Body'].read().decode('utf-8'))
                        results.append(data)
                    except Exception as e:
                        print(f"⚠ Error loading {key}: {e}")
        
        print(f"✓ Loaded {json_count} JSON files")
        
    except Exception as e:
        print(f"⚠ Error reading from S3: {e}")
        return []
    
    return results


def analyze_costs(audit_data: List[Dict]) -> Tuple[Dict, List[Dict]]:
    """
    Analyze cost and token data from audit files
    
    Returns:
        (summary_stats, per_product_stats)
    """
    
    # Per-product stats
    products = {}
    
    for record in audit_data:
        asin = record.get('asin', 'unknown')
        
        # Extract cost and token data
        tokens_used = record.get('tokens_used', 0)
        api_cost = record.get('api_cost', 0)
        processing_time = record.get('processing_time_sec', 0)
        status = record.get('status', 'unknown')
        
        # Get token breakdown from metadata
        metadata = record.get('_metadata', {})
        tokens_breakdown = metadata.get('tokens_used', {})  # ✅ FIXED: was 'tokens'
        prompt_tokens = tokens_breakdown.get('prompt', 0)
        completion_tokens = tokens_breakdown.get('completion', 0)
        
        # If api_cost is missing/0 but tokens exist, calculate cost (for old audit files)
        if (not api_cost or api_cost == 0) and tokens_used == 0 and tokens_breakdown:
            # Use tokens from metadata
            tokens_used = tokens_breakdown.get('total', 0)
            # Calculate cost (GPT-4o mini pricing: $0.150/1M input, $0.600/1M output)
            if prompt_tokens > 0 or completion_tokens > 0:
                input_cost = (prompt_tokens / 1_000_000) * 0.150
                output_cost = (completion_tokens / 1_000_000) * 0.600
                api_cost = input_cost + output_cost
        
        # Keep the most recent/complete record for each ASIN
        if asin not in products or status in ['success', 'step3_complete']:
            products[asin] = {
                'asin': asin,
                'status': status,
                'tokens_used': tokens_used,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'api_cost': api_cost,
                'processing_time_sec': processing_time,
                'category': record.get('category', ''),
                'subcategory': record.get('subcategory', ''),
                'high_level_category': record.get('high_level_category', '')
            }
    
    # Calculate summary stats
    success_products = [p for p in products.values() if p['status'] in ['success', 'step3_complete']]
    filtered_products = [p for p in products.values() if p['status'] in ['filtered', 'REMOVE']]
    error_products = [p for p in products.values() if p['status'] == 'error']
    
    total_cost = sum(p['api_cost'] for p in success_products)
    total_tokens = sum(p['tokens_used'] for p in success_products)
    total_prompt_tokens = sum(p['prompt_tokens'] for p in success_products)
    total_completion_tokens = sum(p['completion_tokens'] for p in success_products)
    
    avg_cost = total_cost / len(success_products) if success_products else 0
    avg_tokens = total_tokens / len(success_products) if success_products else 0
    avg_time = sum(p['processing_time_sec'] for p in success_products) / len(success_products) if success_products else 0
    
    summary = {
        'total_products': len(products),
        'success_count': len(success_products),
        'filtered_count': len(filtered_products),
        'error_count': len(error_products),
        'total_cost': total_cost,
        'total_tokens': total_tokens,
        'prompt_tokens': total_prompt_tokens,
        'completion_tokens': total_completion_tokens,
        'avg_cost_per_product': avg_cost,
        'avg_tokens_per_product': avg_tokens,
        'avg_processing_time_sec': avg_time,
        'analyzed_at': datetime.utcnow().isoformat()
    }
    
    return summary, list(products.values())


def update_dynamodb(table_name: str, file_id: str, run_id: str, summary: Dict, region: str = 'us-east-2'):
    """Update DynamoDB with cost summary"""
    
    if not AWS_AVAILABLE:
        print("⚠ Error: boto3 not available for DynamoDB operations")
        return False
    
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    
    # Convert floats to Decimal for DynamoDB
    summary_decimal = json.loads(json.dumps(summary), parse_float=Decimal)
    
    # Create processing key (convention: file_id + "_processing")
    processing_key = f"{file_id}_processing"
    
    try:
        # Update or create the cost summary record
        response = table.update_item(
            Key={
                'asin': processing_key,
                'run_id': run_id
            },
            UpdateExpression="""
                SET cost_summary = :summary,
                    total_cost = :total_cost,
                    total_tokens = :total_tokens,
                    prompt_tokens = :prompt_tokens,
                    completion_tokens = :completion_tokens,
                    success_count = :success,
                    filtered_count = :filtered,
                    error_count = :errors,
                    avg_cost = :avg_cost,
                    updated_at = :updated_at
            """,
            ExpressionAttributeValues={
                ':summary': summary_decimal,
                ':total_cost': Decimal(str(summary['total_cost'])),
                ':total_tokens': summary['total_tokens'],
                ':prompt_tokens': summary['prompt_tokens'],
                ':completion_tokens': summary['completion_tokens'],
                ':success': summary['success_count'],
                ':filtered': summary['filtered_count'],
                ':errors': summary['error_count'],
                ':avg_cost': Decimal(str(summary['avg_cost_per_product'])),
                ':updated_at': datetime.utcnow().isoformat()
            },
            ReturnValues='UPDATED_NEW'
        )
        
        print(f"✓ Updated DynamoDB table '{table_name}'")
        print(f"  Key: {processing_key}/{run_id}")
        return True
        
    except Exception as e:
        print(f"⚠ Error updating DynamoDB: {e}")
        return False


def update_file_tracker(file_id: str, run_id: str, summary: Dict, tracking_path: str = 'data/tracking'):
    """Update FileTracker JSON with cost summary (simulates DynamoDB for local mode)"""
    
    tracking_file = Path(tracking_path) / 'files_status.json'
    
    if not tracking_file.exists():
        print(f"⚠ Error: Tracking file not found: {tracking_file}")
        return False
    
    try:
        # Load existing tracking data
        with open(tracking_file, 'r') as f:
            tracking_data = json.load(f)
        
        # Find the file entry (might have "uncoded_" prefix)
        file_key = None
        for key in tracking_data.keys():
            if key == file_id or key == f"uncoded_{file_id}":
                file_key = key
                break
        
        if not file_key:
            print(f"⚠ Error: File '{file_id}' not found in tracking data")
            print(f"   Available files: {list(tracking_data.keys())}")
            return False
        
        # Update the file entry with cost data
        tracking_data[file_key]['total_cost'] = summary['total_cost']
        tracking_data[file_key]['total_tokens'] = summary['total_tokens']
        tracking_data[file_key]['input_tokens'] = summary['prompt_tokens']
        tracking_data[file_key]['output_tokens'] = summary['completion_tokens']
        tracking_data[file_key]['success'] = summary['success_count']
        tracking_data[file_key]['filtered'] = summary['filtered_count']
        tracking_data[file_key]['errors'] = summary['error_count']
        tracking_data[file_key]['last_run_id'] = run_id
        tracking_data[file_key]['cost_updated_at'] = datetime.utcnow().isoformat()
        
        # Save updated tracking data
        with open(tracking_file, 'w') as f:
            json.dump(tracking_data, f, indent=2, default=str)
        
        print(f"✓ Updated FileTracker JSON: {tracking_file}")
        print(f"  Key: {file_key}")
        return True
        
    except Exception as e:
        print(f"⚠ Error updating FileTracker: {e}")
        return False


def print_summary(summary: Dict, per_product: List[Dict]):
    """Print cost analysis summary"""
    
    print("\n" + "="*80)
    print("COST ANALYSIS SUMMARY")
    print("="*80)
    
    print(f"\nOVERALL STATS:")
    print(f"   Total Products: {summary['total_products']:,}")
    print(f"   ✓ Success: {summary['success_count']:,}")
    print(f"   Filtered: {summary['filtered_count']:,}")
    print(f"   Errors: {summary['error_count']:,}")
    
    print(f"\n💰 COSTS:")
    print(f"   Total API Cost: ${summary['total_cost']:.4f}")
    print(f"   Avg per product: ${summary['avg_cost_per_product']:.6f}")
    
    print(f"\n🔢 TOKENS:")
    print(f"   Total: {summary['total_tokens']:,}")
    print(f"   Input (prompt): {summary['prompt_tokens']:,}")
    print(f"   Output (completion): {summary['completion_tokens']:,}")
    print(f"   Avg per product: {summary['avg_tokens_per_product']:.0f}")
    
    print(f"\n⏱️  TIMING:")
    print(f"   Avg processing time: {summary['avg_processing_time_sec']:.2f}s per product")
    
    # Top 5 most expensive products
    if per_product:
        sorted_products = sorted(per_product, key=lambda x: x['api_cost'], reverse=True)[:5]
        print(f"\n💸 TOP 5 MOST EXPENSIVE:")
        for i, p in enumerate(sorted_products, 1):
            print(f"   {i}. {p['asin']}: ${p['api_cost']:.4f} ({p['tokens_used']:,} tokens)")
    
    print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(description='Analyze costs from audit files and update tracking/DynamoDB')
    parser.add_argument('--file-id', required=True, help='File ID (e.g., 100_records)')
    parser.add_argument('--run-id', required=True, help='Run ID (e.g., run_9)')
    parser.add_argument('--base-path', default='data', help='Base path for local data (default: data)')
    parser.add_argument('--s3', action='store_true', help='Read from S3 instead of local')
    parser.add_argument('--bucket', help='S3 bucket name (required if --s3)')
    parser.add_argument('--audit-prefix', default='audit/', help='S3 audit prefix (default: audit/)')
    parser.add_argument('--dynamodb-table', help='DynamoDB table name (for AWS mode)')
    parser.add_argument('--region', default='us-east-2', help='AWS region (default: us-east-2)')
    parser.add_argument('--update-db', action='store_true', help='Update DynamoDB with results (AWS mode)')
    parser.add_argument('--update-tracker', action='store_true', help='Update FileTracker JSON (local mode)')
    parser.add_argument('--tracking-path', default='data/tracking', help='FileTracker path (default: data/tracking)')
    
    args = parser.parse_args()
    
    print(f"\nAnalyzing costs for: {args.file_id}/{args.run_id}")
    
    # Load audit files
    if args.s3:
        if not args.bucket:
            print("⚠ Error: --bucket required when using --s3")
            return 1
        
        if not AWS_AVAILABLE:
            print("⚠ Error: boto3 required for S3 operations")
            return 1
        
        audit_data = load_audit_files_s3(args.bucket, args.file_id, args.run_id, args.audit_prefix)
    else:
        audit_data = load_audit_files_local(args.base_path, args.file_id, args.run_id)
    
    if not audit_data:
        print("⚠ No audit data found!")
        return 1
    
    print(f"✓ Loaded {len(audit_data)} audit records")
    
    # Analyze costs
    summary, per_product = analyze_costs(audit_data)
    
    # Print summary
    print_summary(summary, per_product)
    
    # Update DynamoDB if requested (AWS mode)
    if args.update_db:
        if not args.dynamodb_table:
            print("⚠ Error: --dynamodb-table required when using --update-db")
            return 1
        
        if not AWS_AVAILABLE:
            print("⚠ Error: boto3 required for DynamoDB operations")
            return 1
        
        print(f"\nUpdating DynamoDB...")
        update_dynamodb(args.dynamodb_table, args.file_id, args.run_id, summary, args.region)
    
    # Update FileTracker JSON if requested (local mode)
    if args.update_tracker:
        print(f"\nUpdating FileTracker JSON...")
        update_file_tracker(args.file_id, args.run_id, summary, args.tracking_path)
    
    print("\n✓ Cost analysis complete!")
    return 0


if __name__ == '__main__':
    exit(main())

