"""
File Tracker - Track processing status of uploaded files

Supports two modes:
- LOCAL: Uses JSON file (data/tracking/file_tracker.json)
- AWS: Uses DynamoDB table

Tracks files by extracting ID from filename:
- "uncoded_amz_p5_2025.csv" → file_id = "amz_p5_2025"
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum

# Try to import boto3 (only needed for AWS mode)
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


class FileStatus(Enum):
    """Processing status for files"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileTracker:
    """
    Track file processing status in local JSON or DynamoDB
    
    Usage:
        # Local mode (development/testing)
        tracker = FileTracker(mode='local')
        
        # AWS mode (production)
        tracker = FileTracker(
            mode='aws',
            dynamodb_config={
                'table_name': 'processing-state-table',
                'region': 'us-east-2'
            }
        )
    """
    
    def __init__(
        self,
        mode: str = 'local',
        tracking_file: str = 'data/tracking/file_tracker.json',
        dynamodb_config: Optional[Dict[str, str]] = None
    ):
        """
        Initialize file tracker
        
        Args:
            mode: 'local' or 'aws'
            tracking_file: Path to JSON file for local mode
            dynamodb_config: Configuration for AWS mode with keys:
                - table_name: DynamoDB table name
                - region: AWS region (default: us-east-2)
        
        Raises:
            ValueError: If mode is invalid or required config missing
            ImportError: If AWS mode requested but boto3 not installed
        """
        self.mode = mode.lower()
        
        if self.mode not in ['local', 'aws']:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'local' or 'aws'")
        
        if self.mode == 'local':
            self._init_local(tracking_file)
        elif self.mode == 'aws':
            self._init_aws(dynamodb_config)
    
    def _init_local(self, tracking_file: str):
        """Initialize local JSON storage"""
        self.tracking_file = Path(tracking_file)
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing data or create empty
        if self.tracking_file.exists():
            with open(self.tracking_file, 'r') as f:
                self.data = json.load(f)
        else:
            self.data = {}
            self._save_local()
    
    def _init_aws(self, dynamodb_config: Optional[Dict[str, str]]):
        """Initialize AWS DynamoDB storage"""
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 is required for AWS mode. "
                "Install with: pip install boto3"
            )
        
        if not dynamodb_config:
            raise ValueError("dynamodb_config is required for AWS mode")
        
        if 'table_name' not in dynamodb_config:
            raise ValueError("dynamodb_config must include 'table_name'")
        
        self.table_name = dynamodb_config['table_name']
        self.region = dynamodb_config.get('region', 'us-east-2')
        
        # Initialize DynamoDB
        try:
            dynamodb = boto3.resource('dynamodb', region_name=self.region)
            self.table = dynamodb.Table(self.table_name)
        except NoCredentialsError:
            raise ValueError(
                "AWS credentials not found. "
                "Configure with: aws configure"
            )
    
    def _save_local(self):
        """Save data to local JSON file"""
        with open(self.tracking_file, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    # ========================================================================
    # FILE ID EXTRACTION
    # ========================================================================
    
    @staticmethod
    def _extract_file_id(filename: str) -> str:
        """
        Extract tracking ID from filename
        
        Pattern: uncoded_*.csv → extract *
        
        Args:
            filename: Input filename
        
        Returns:
            File ID for tracking
        
        Examples:
            "uncoded_amz_p5_2025.csv" → "amz_p5_2025"
            "uncoded_test.csv" → "test"
            "other_file.csv" → "other_file"
        """
        # Remove "uncoded_" prefix if present
        if filename.startswith('uncoded_'):
            file_id = filename.replace('uncoded_', '', 1)
        else:
            file_id = filename
        
        # Remove ".csv" suffix
        file_id = file_id.replace('.csv', '')
        
        return file_id
    
    # ========================================================================
    # QUERY METHODS
    # ========================================================================
    
    def is_file_processed(self, filename: str) -> bool:
        """
        Check if file has been successfully processed
        
        Args:
            filename: File name (e.g., 'uncoded_amz_p5_2025.csv')
        
        Returns:
            True if file is completed, False otherwise
        """
        status = self.get_file_status(filename)
        if not status:
            return False
        
        return status.get('status') == FileStatus.COMPLETED.value
    
    def get_file_status(self, filename: str) -> Optional[Dict]:
        """
        Get processing status for a file
        
        Args:
            filename: File name
        
        Returns:
            Dictionary with file info, or None if not found
        """
        file_id = self._extract_file_id(filename)
        
        if self.mode == 'local':
            return self.data.get(file_id)
        else:
            return self._get_dynamodb_item(file_id)
    
    def _get_dynamodb_item(self, file_id: str) -> Optional[Dict]:
        """Get item from DynamoDB"""
        try:
            response = self.table.get_item(Key={'file_id': file_id})
            return response.get('Item')
        except ClientError as e:
            # Item not found is OK, return None
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return None
            raise IOError(f"Failed to get item from DynamoDB: {e}")
    
    # ========================================================================
    # UPDATE METHODS
    # ========================================================================
    
    def start_processing(
        self,
        filename: str,
        product_count: int = 0
    ) -> Dict:
        """
        Mark file as started processing
        
        Args:
            filename: File name
            product_count: Number of products in file
        
        Returns:
            File record
        """
        file_id = self._extract_file_id(filename)
        
        record = {
            'file_id': file_id,
            'filename': filename,
            'status': FileStatus.PROCESSING.value,
            'product_count': product_count,
            'start_time': datetime.utcnow().isoformat(),
            'end_time': None,
            'removed_count': 0,
            'classified_count': 0,
            'error_message': None
        }
        
        if self.mode == 'local':
            self.data[file_id] = record
            self._save_local()
        else:
            self._put_dynamodb_item(record)
        
        return record
    
    def complete_processing(
        self,
        filename: str,
        removed_count: int = 0,
        classified_count: int = 0
    ) -> Dict:
        """
        Mark file as completed
        
        Args:
            filename: File name
            removed_count: Number of products removed (non-supplements)
            classified_count: Number of products classified
        
        Returns:
            Updated file record
        """
        file_id = self._extract_file_id(filename)
        
        updates = {
            'status': FileStatus.COMPLETED.value,
            'end_time': datetime.utcnow().isoformat(),
            'removed_count': removed_count,
            'classified_count': classified_count
        }
        
        if self.mode == 'local':
            if file_id in self.data:
                self.data[file_id].update(updates)
            else:
                # Create new record if doesn't exist
                self.data[file_id] = {
                    'file_id': file_id,
                    'filename': filename,
                    **updates
                }
            self._save_local()
            return self.data[file_id]
        else:
            return self._update_dynamodb_item(file_id, updates)
    
    def mark_failed(
        self,
        filename: str,
        error_message: str
    ) -> Dict:
        """
        Mark file processing as failed
        
        Args:
            filename: File name
            error_message: Error description
        
        Returns:
            Updated file record
        """
        file_id = self._extract_file_id(filename)
        
        updates = {
            'status': FileStatus.FAILED.value,
            'end_time': datetime.utcnow().isoformat(),
            'error_message': error_message
        }
        
        if self.mode == 'local':
            if file_id in self.data:
                self.data[file_id].update(updates)
            else:
                self.data[file_id] = {
                    'file_id': file_id,
                    'filename': filename,
                    **updates
                }
            self._save_local()
            return self.data[file_id]
        else:
            return self._update_dynamodb_item(file_id, updates)
    
    def _put_dynamodb_item(self, item: Dict):
        """Put item to DynamoDB"""
        try:
            self.table.put_item(Item=item)
        except ClientError as e:
            raise IOError(f"Failed to put item to DynamoDB: {e}")
    
    def _update_dynamodb_item(self, file_id: str, updates: Dict) -> Dict:
        """Update item in DynamoDB"""
        try:
            # Build update expression
            update_expr = "SET " + ", ".join(
                f"#{k} = :{k}" for k in updates.keys()
            )
            
            expr_attr_names = {f"#{k}": k for k in updates.keys()}
            expr_attr_values = {f":{k}": v for k, v in updates.items()}
            
            response = self.table.update_item(
                Key={'file_id': file_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
                ReturnValues='ALL_NEW'
            )
            
            return response.get('Attributes', {})
            
        except ClientError as e:
            raise IOError(f"Failed to update DynamoDB item: {e}")
    
    # ========================================================================
    # LIST & SUMMARY METHODS
    # ========================================================================
    
    def list_all_files(self) -> List[Dict]:
        """
        List all tracked files
        
        Returns:
            List of file records
        """
        if self.mode == 'local':
            return list(self.data.values())
        else:
            return self._scan_dynamodb()
    
    def _scan_dynamodb(self) -> List[Dict]:
        """Scan all items from DynamoDB"""
        try:
            response = self.table.scan()
            return response.get('Items', [])
        except ClientError as e:
            raise IOError(f"Failed to scan DynamoDB: {e}")
    
    def get_summary(self) -> Dict:
        """
        Get summary statistics
        
        Returns:
            Dictionary with counts by status and totals
        """
        all_files = self.list_all_files()
        
        summary = {
            'total_files': len(all_files),
            'pending': 0,
            'processing': 0,
            'completed': 0,
            'failed': 0,
            'total_products_processed': 0,
            'total_removed': 0,
            'total_classified': 0
        }
        
        for file in all_files:
            status = file.get('status', 'pending')
            summary[status] = summary.get(status, 0) + 1
            
            if status == FileStatus.COMPLETED.value:
                summary['total_products_processed'] += file.get('product_count', 0)
                summary['total_removed'] += file.get('removed_count', 0)
                summary['total_classified'] += file.get('classified_count', 0)
        
        return summary
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def get_info(self) -> Dict[str, str]:
        """Get information about tracker configuration"""
        if self.mode == 'local':
            return {
                'mode': 'local',
                'tracking_file': str(self.tracking_file)
            }
        else:
            return {
                'mode': 'aws',
                'region': self.region,
                'table_name': self.table_name
            }


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_file_tracker_from_env() -> FileTracker:
    """
    Create file tracker from environment variables
    
    Environment variables:
        STORAGE_MODE: 'local' or 'aws' (default: 'local')
        
        For local mode:
        - TRACKING_FILE: Path to JSON file (default: 'data/tracking/file_tracker.json')
        
        For AWS mode:
        - DYNAMODB_TABLE: DynamoDB table name (required)
        - AWS_REGION: AWS region (default: 'us-east-2')
    
    Returns:
        Configured FileTracker instance
    """
    mode = os.getenv('STORAGE_MODE', 'local')
    
    if mode == 'aws':
        dynamodb_config = {
            'table_name': os.getenv('DYNAMODB_TABLE'),
            'region': os.getenv('AWS_REGION', 'us-east-2')
        }
        
        if not dynamodb_config['table_name']:
            raise ValueError("DYNAMODB_TABLE environment variable required for AWS mode")
        
        return FileTracker(mode='aws', dynamodb_config=dynamodb_config)
    
    else:
        tracking_file = os.getenv('TRACKING_FILE', 'data/tracking/file_tracker.json')
        return FileTracker(mode='local', tracking_file=tracking_file)


# ============================================================================
# MAIN - For testing
# ============================================================================

if __name__ == "__main__":
    import sys
    
    print("File Tracker Test")
    print("=" * 50)
    
    # Test local mode
    print("\n1. Testing LOCAL mode...")
    try:
        tracker = FileTracker(mode='local')
        info = tracker.get_info()
        print(f"   Mode: {info['mode']}")
        print(f"   Tracking file: {info['tracking_file']}")
        
        # Test file ID extraction
        test_filename = "uncoded_amz_p5_2025.csv"
        file_id = tracker._extract_file_id(test_filename)
        print(f"   File ID extraction: '{test_filename}' → '{file_id}'")
        
        # Test workflow
        print("\n2. Testing workflow...")
        print(f"   Starting processing: {test_filename}")
        tracker.start_processing(test_filename, product_count=31448)
        
        status = tracker.get_file_status(test_filename)
        print(f"   Status: {status['status']}")
        print(f"   Product count: {status['product_count']}")
        
        print(f"   Completing processing...")
        tracker.complete_processing(
            test_filename,
            removed_count=5200,
            classified_count=26248
        )
        
        # Check if processed
        is_processed = tracker.is_file_processed(test_filename)
        print(f"   Is processed: {is_processed}")
        
        # Get summary
        summary = tracker.get_summary()
        print(f"\n3. Summary:")
        print(f"   Total files: {summary['total_files']}")
        print(f"   Completed: {summary['completed']}")
        print(f"   Total classified: {summary['total_classified']}")
        
        print("\n   ✅ Local mode OK")
        
    except Exception as e:
        print(f"   ❌ Local mode failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n✅ File tracker tests passed!")

