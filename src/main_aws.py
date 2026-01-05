"""
AWS Main - Process products from S3
Reads from S3, processes, and writes results back to S3
Sends SNS notifications on completion
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
from typing import Dict, List
import boto3

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aws.s3_manager import S3Manager
from aws.dynamodb_manager import DynamoDBManager
from core.preprocessing import standardize_dataframe
from pipeline.step1_filter import apply_step1_filter
from pipeline.step2_llm import extract_llm_attributes, extract_attributes_from_llm_result
from pipeline.utils.business_rules import apply_all_business_rules
from pipeline.utils.high_level_category import assign_high_level_category
from core.log_manager import LogManager


def send_notification(sns_topic_arn: str, subject: str, message: str):
    """Send SNS notification"""
    try:
        sns = boto3.client('sns')
        sns.publish(
            TopicArn=sns_topic_arn,
            Subject=subject,
            Message=message
        )
        print(f"📧 Notification sent: {subject}")
    except Exception as e:
        print(f"⚠️  Failed to send notification: {str(e)}")


def process_from_s3(
    input_bucket: str,
    input_key: str,
    output_bucket: str,
    audit_bucket: str,
    dynamodb_table: str,
    run_id: str,
    sns_topic_arn: str = None
):
    """
    Process products from S3
    
    Args:
        input_bucket: S3 bucket with input CSV
        input_key: S3 key for input CSV
        output_bucket: S3 bucket for output
        audit_bucket: S3 bucket for audit logs
        dynamodb_table: DynamoDB table name
        run_id: Unique run ID
        sns_topic_arn: Optional SNS topic for notifications
    """
    
    start_time = datetime.now()
    
    print("="*80)
    print("AWS CLOUD PROCESSING - Bedrock AI Data Enrichment")
    print("="*80)
    print(f"\nRun ID: {run_id}")
    print(f"Input: s3://{input_bucket}/{input_key}")
    print(f"Output: s3://{output_bucket}/")
    print(f"Audit: s3://{audit_bucket}/")
    
    try:
        # Initialize AWS managers
        s3 = S3Manager()
        db = DynamoDBManager(dynamodb_table)
    
    # Read input CSV from S3
    print(f"\n📥 Reading input data...")
    df = s3.read_csv_from_s3(input_bucket, input_key, encoding='latin-1')
    
    if df is None:
        print("❌ Failed to read input file")
        return
    
    # Standardize
    df = standardize_dataframe(df)
    total_records = len(df)
    print(f"✅ Loaded {total_records:,} records")
    
    # Create log manager (will write to local /tmp then upload to S3)
    input_filename = Path(input_key).stem
    log_manager = LogManager(
        input_filename=input_filename,
        base_path='/tmp/bedrock-data'
    )
    
    print(f"\n🚀 Processing {total_records} records...")
    
    results = []
    
    for idx, record in df.iterrows():
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
                # Filtered - write to DynamoDB
                db.put_record(
                    asin=asin,
                    run_id=run_id,
                    status='filtered',
                    data={'reason': step1_result['filter_reason']}
                )
                continue
            
            # Step 2: LLM extraction
            llm_result = extract_llm_attributes(title, asin, product_id, log_manager)
            
            if not llm_result['success']:
                # Error
                db.put_record(
                    asin=asin,
                    run_id=run_id,
                    status='error',
                    data={'error': llm_result.get('error', 'Unknown error')}
                )
                continue
            
            # Extract attributes
            attrs = extract_attributes_from_llm_result(llm_result['data'])
            
            # Step 3: Business rules
            business_rules = apply_all_business_rules(
                attrs['ingredients'],
                attrs['age'],
                attrs['gender'],
                title
            )
            
            # Build result
            result = {
                'asin': asin,
                'title': title,
                'category': business_rules['category'],
                'subcategory': business_rules['subcategory'],
                'primary_ingredient': business_rules['primary_ingredient'],
                'age': attrs['age'],
                'gender': attrs['gender'],
                'form': attrs['form'],
                'reasoning': business_rules.get('reasoning', '')
            }
            
            results.append(result)
            
            # Write to DynamoDB
            db.put_record(
                asin=asin,
                run_id=run_id,
                status='success',
                data=result
            )
            
            print(f"✅ [{product_id}/{total_records}] {asin}")
            
        except Exception as e:
            print(f"❌ [{product_id}/{total_records}] {asin}: {str(e)}")
            db.put_record(
                asin=asin,
                run_id=run_id,
                status='error',
                data={'error': str(e)}
            )
    
    # Convert results to DataFrame
    if results:
        results_df = pd.DataFrame(results)
        
        # Write to S3
        output_key = f"runs/{run_id}/{input_filename}_coded.csv"
        s3.write_csv_to_s3(results_df, output_bucket, output_key)
        
        print(f"\n✅ Processing complete!")
        print(f"   Processed: {len(results)} products")
        print(f"   Output: s3://{output_bucket}/{output_key}")
    
    # Upload audit logs to S3
    audit_prefix = f"runs/{run_id}/audit"
    audit_dir = Path(f'/tmp/bedrock-data/audit/{input_filename}')
    if audit_dir.exists():
        count = s3.upload_directory(audit_dir, audit_bucket, audit_prefix)
        print(f"   Uploaded {count} audit files")
    
    # Send success notification
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds() / 60
    
    if sns_topic_arn:
        message = f"""
✅ Processing Complete!

File: {input_key}
Run ID: {run_id}
Total Products: {total_records:,}
Processed: {len(results):,}
Duration: {duration:.1f} minutes

Output: s3://{output_bucket}/runs/{run_id}/{input_filename}_coded.csv
Audit: s3://{audit_bucket}/runs/{run_id}/audit/

Status Summary:
- Success: {len(results)}
- Total: {total_records}
"""
        send_notification(sns_topic_arn, f"✅ Processing Complete - {input_filename}", message)
    
    except Exception as e:
        # Send error notification
        if sns_topic_arn:
            error_message = f"""
❌ Processing Failed!

File: {input_key}
Run ID: {run_id}
Error: {str(e)}

Please check CloudWatch Logs for details.
"""
            send_notification(sns_topic_arn, f"❌ Processing Failed - {input_filename}", error_message)
        raise


if __name__ == '__main__':
    # Get parameters from environment or command line
    INPUT_BUCKET = os.getenv('INPUT_BUCKET', 'bedrock-ai-data-enrichment-input-081671069810')
    OUTPUT_BUCKET = os.getenv('OUTPUT_BUCKET', 'bedrock-ai-data-enrichment-output-081671069810')
    AUDIT_BUCKET = os.getenv('AUDIT_BUCKET', 'bedrock-ai-data-enrichment-audit-081671069810')
    DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE', 'bedrock-ai-data-enrichment-processing-state')
    SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')
    
    INPUT_KEY = sys.argv[1] if len(sys.argv) > 1 else 'sample_10_test.csv'
    RUN_ID = sys.argv[2] if len(sys.argv) > 2 else f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    process_from_s3(
        input_bucket=INPUT_BUCKET,
        input_key=INPUT_KEY,
        output_bucket=OUTPUT_BUCKET,
        audit_bucket=AUDIT_BUCKET,
        dynamodb_table=DYNAMODB_TABLE,
        run_id=RUN_ID,
        sns_topic_arn=SNS_TOPIC_ARN
    )

