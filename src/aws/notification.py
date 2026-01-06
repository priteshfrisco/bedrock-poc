"""
AWS SNS Notification Manager
Handles email notifications for processing status
"""

import boto3
from typing import Optional


def send_notification(sns_topic_arn: str, subject: str, message: str):
    """Send SNS notification (AWS mode only)"""
    try:
        sns = boto3.client('sns')
        sns.publish(
            TopicArn=sns_topic_arn,
            Subject=subject,
            Message=message
        )
        print(f"Notification sent: {subject}")
    except Exception as e:
        print(f"Failed to send notification: {str(e)}")


def generate_presigned_url(bucket: str, key: str, expiration: int = 604800) -> str:
    """
    Generate a pre-signed URL for S3 object download
    Default expiration: 7 days (604800 seconds)
    """
    try:
        s3_client = boto3.client('s3')
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        print(f"Failed to generate pre-signed URL: {str(e)}")
        return f"s3://{bucket}/{key}"


def send_success_notification(
    sns_topic_arn: str,
    input_key: str,
    input_filename: str,
    run_folder: str,
    total_records: int,
    enriched_count: int,
    filtered_count: int,
    error_count: int,
    duration_minutes: float,
    s3_bucket: str,
    output_prefix: str,
    audit_prefix: str,
    logs_prefix: str,
    region: str = "us-east-2"
):
    """Send success notification with results summary"""
    # AWS Console S3 links
    console_bucket = f"https://s3.console.aws.amazon.com/s3/buckets/{s3_bucket}"
    console_output = f"{console_bucket}?prefix={output_prefix}{input_filename}/{run_folder}/"
    
    message = f"""
✓ Processing Complete

File: {input_key}
Run: {run_folder}
Duration: {duration_minutes:.1f} minutes

Results:
---------------------------------------
Total Products:           {total_records:,}
Enriched (Full LLM):      {enriched_count:,}
Filtered (Non-Supplements): {filtered_count:,}
Errors:                   {error_count:,}
---------------------------------------

AWS Console Links:
{console_output}

Download via AWS CLI:
aws s3 cp s3://{s3_bucket}/{output_prefix}{input_filename}/{run_folder}/{input_filename}_coded.csv .

S3 Locations:
- Output: s3://{s3_bucket}/{output_prefix}{input_filename}/{run_folder}/{input_filename}_coded.csv
- Audit:  s3://{s3_bucket}/{audit_prefix}{input_filename}/{run_folder}/audit/
- Logs:   s3://{s3_bucket}/{logs_prefix}{input_filename}/{run_folder}/logs/
"""
    send_notification(sns_topic_arn, f"✓ Processing Complete - {input_filename}", message)


def send_error_notification(
    sns_topic_arn: str,
    input_key: str,
    run_folder: Optional[str],
    error: str,
    s3_bucket: str = None,
    region: str = "us-east-2"
):
    """Send error notification"""
    from pathlib import Path
    
    console_link = ""
    if s3_bucket and run_folder:
        console_link = f"\nAWS Console: https://s3.console.aws.amazon.com/s3/buckets/{s3_bucket}?prefix=logs/{Path(input_key).name}/{run_folder}/"
    
    error_message = f"""
⚠ Processing Failed

File: {input_key}
Run: {run_folder if run_folder else 'N/A'}
Error: {error}
{console_link}

Check CloudWatch Logs for details.
"""
    send_notification(sns_topic_arn, f"⚠ Processing Failed - {Path(input_key).stem}", error_message)


def send_invalid_filename_notification(
    sns_topic_arn: str,
    input_filename: str
):
    """Send notification for invalid filename"""
    error_msg = f"""
⚠ Invalid Filename

File: {input_filename}

Error: Input files must start with 'uncoded_'

Valid examples:
- uncoded_products.csv
- uncoded_january_2026.csv
- UNCODED_test.csv

Please rename your file and upload again.
"""
    send_notification(sns_topic_arn, f"⚠ Invalid Filename - {input_filename}", error_msg)


def send_processing_started_notification(
    sns_topic_arn: str,
    input_key: str,
    input_filename: str,
    run_folder: str,
    total_records: int,
    s3_bucket: str,
    region: str = "us-east-2"
):
    """Send notification when processing starts"""
    console_bucket = f"https://s3.console.aws.amazon.com/s3/buckets/{s3_bucket}"
    
    message = f"""
Processing Started

File: {input_key}
Run: {run_folder}
Total Products: {total_records:,}

Status: Processing in progress

You will receive another email when processing completes.

AWS Console: {console_bucket}
"""
    send_notification(sns_topic_arn, f"Processing Started - {input_filename}", message)

