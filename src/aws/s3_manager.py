"""
AWS S3 Integration Module
Handles reading from and writing to S3 buckets
"""

import boto3
import pandas as pd
from pathlib import Path
from typing import Optional, List
import io
import json
from datetime import datetime


class S3Manager:
    """Manages S3 operations for input/output/audit data"""
    
    def __init__(self, region: str = 'us-east-2'):
        """
        Initialize S3 client
        
        Args:
            region: AWS region (default: us-east-2)
        """
        self.s3 = boto3.client('s3', region_name=region)
        self.region = region
    
    def list_input_files(self, bucket: str, prefix: str = '') -> List[str]:
        """
        List CSV files in input bucket
        
        Args:
            bucket: S3 bucket name
            prefix: Optional prefix to filter files
            
        Returns:
            List of S3 keys for CSV files
        """
        try:
            response = self.s3.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                return []
            
            # Filter for CSV files only
            csv_files = [
                obj['Key'] for obj in response['Contents']
                if obj['Key'].endswith('.csv')
            ]
            
            return csv_files
            
        except Exception as e:
            print(f"❌ Error listing files in s3://{bucket}/{prefix}: {str(e)}")
            return []
    
    def read_csv_from_s3(self, bucket: str, key: str, encoding: str = 'utf-8') -> Optional[pd.DataFrame]:
        """
        Read CSV file from S3 into DataFrame
        
        Args:
            bucket: S3 bucket name
            key: S3 object key
            encoding: File encoding (default: utf-8, try latin-1 if fails)
            
        Returns:
            pandas DataFrame or None if error
        """
        try:
            print(f"📥 Reading s3://{bucket}/{key}")
            
            response = self.s3.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read()
            
            # Try specified encoding first
            try:
                df = pd.read_csv(io.BytesIO(content), encoding=encoding)
            except UnicodeDecodeError:
                # Fallback to latin-1
                print(f"⚠️  UTF-8 failed, trying latin-1 encoding...")
                df = pd.read_csv(io.BytesIO(content), encoding='latin-1')
            
            print(f"✅ Loaded {len(df):,} records")
            return df
            
        except Exception as e:
            print(f"❌ Error reading CSV from S3: {str(e)}")
            return None
    
    def write_csv_to_s3(self, df: pd.DataFrame, bucket: str, key: str) -> bool:
        """
        Write DataFrame to S3 as CSV
        
        Args:
            df: pandas DataFrame
            bucket: S3 bucket name
            key: S3 object key
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"📤 Writing s3://{bucket}/{key}")
            
            # Convert DataFrame to CSV in memory
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            
            # Upload to S3
            self.s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=csv_buffer.getvalue(),
                ContentType='text/csv'
            )
            
            print(f"✅ Uploaded {len(df):,} records")
            return True
            
        except Exception as e:
            print(f"❌ Error writing CSV to S3: {str(e)}")
            return False
    
    def write_json_to_s3(self, data: dict, bucket: str, key: str) -> bool:
        """
        Write JSON data to S3
        
        Args:
            data: Dictionary to write as JSON
            bucket: S3 bucket name
            key: S3 object key
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=json.dumps(data, indent=2),
                ContentType='application/json'
            )
            return True
            
        except Exception as e:
            print(f"❌ Error writing JSON to S3: {str(e)}")
            return False
    
    def upload_directory(self, local_dir: Path, bucket: str, s3_prefix: str) -> int:
        """
        Upload entire directory to S3
        
        Args:
            local_dir: Local directory path
            bucket: S3 bucket name
            s3_prefix: S3 prefix for uploaded files
            
        Returns:
            Number of files uploaded
        """
        count = 0
        
        try:
            for file_path in local_dir.rglob('*'):
                if file_path.is_file():
                    # Calculate relative path
                    relative_path = file_path.relative_to(local_dir)
                    s3_key = f"{s3_prefix}/{relative_path}".replace('\\', '/')
                    
                    # Upload file
                    self.s3.upload_file(
                        str(file_path),
                        bucket,
                        s3_key
                    )
                    count += 1
            
            print(f"✅ Uploaded {count} files to s3://{bucket}/{s3_prefix}/")
            return count
            
        except Exception as e:
            print(f"❌ Error uploading directory: {str(e)}")
            return count
    
    def generate_presigned_url(self, bucket: str, key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate pre-signed URL for S3 object
        
        Args:
            bucket: S3 bucket name
            key: S3 object key
            expiration: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            Pre-signed URL or None if error
        """
        try:
            url = self.s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=expiration
            )
            return url
            
        except Exception as e:
            print(f"❌ Error generating presigned URL: {str(e)}")
            return None


if __name__ == '__main__':
    # Test S3 connectivity
    s3_manager = S3Manager()
    
    # Test bucket (replace with your actual bucket name)
    test_bucket = 'bedrock-ai-data-enrichment-input-081671069810'
    
    print("="*80)
    print("Testing S3 Connectivity")
    print("="*80)
    
    files = s3_manager.list_input_files(test_bucket)
    print(f"\nFiles in {test_bucket}:")
    for f in files:
        print(f"  - {f}")
    
    if not files:
        print("  (No files found - bucket is empty)")

