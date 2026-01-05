"""
DynamoDB State Tracking Module
Tracks processing status for each product (ASIN)
"""

import boto3
from datetime import datetime
from typing import Dict, List, Optional
from decimal import Decimal
import json


class DynamoDBManager:
    """Manages DynamoDB operations for tracking processing state"""
    
    def __init__(self, table_name: str, region: str = 'us-east-2'):
        """
        Initialize DynamoDB client
        
        Args:
            table_name: DynamoDB table name
            region: AWS region (default: us-east-2)
        """
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.table = self.dynamodb.Table(table_name)
        self.table_name = table_name
        self.region = region
    
    def put_record(self, asin: str, run_id: str, status: str, data: Dict) -> bool:
        """
        Store or update processing record
        
        Args:
            asin: Product ASIN
            run_id: Processing run ID
            status: Status (processing, success, error, filtered)
            data: Additional data to store
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert floats to Decimal for DynamoDB
            data_decimal = json.loads(json.dumps(data), parse_float=Decimal)
            
            item = {
                'asin': asin,
                'run_id': run_id,
                'status': status,
                'updated_at': datetime.utcnow().isoformat(),
                **data_decimal
            }
            
            self.table.put_item(Item=item)
            return True
            
        except Exception as e:
            print(f"❌ Error putting record to DynamoDB: {str(e)}")
            return False
    
    def get_record(self, asin: str, run_id: str) -> Optional[Dict]:
        """
        Get processing record
        
        Args:
            asin: Product ASIN
            run_id: Processing run ID
            
        Returns:
            Record dict or None if not found
        """
        try:
            response = self.table.get_item(
                Key={'asin': asin, 'run_id': run_id}
            )
            return response.get('Item')
            
        except Exception as e:
            print(f"❌ Error getting record from DynamoDB: {str(e)}")
            return None
    
    def query_by_status(self, status: str, run_id: Optional[str] = None) -> List[Dict]:
        """
        Query records by status
        
        Args:
            status: Status to query (success, error, filtered, processing)
            run_id: Optional run_id to filter
            
        Returns:
            List of records
        """
        try:
            query_params = {
                'IndexName': 'StatusIndex',
                'KeyConditionExpression': 'status = :status',
                'ExpressionAttributeValues': {':status': status}
            }
            
            if run_id:
                query_params['FilterExpression'] = 'run_id = :run_id'
                query_params['ExpressionAttributeValues'][':run_id'] = run_id
            
            response = self.table.query(**query_params)
            return response.get('Items', [])
            
        except Exception as e:
            print(f"❌ Error querying DynamoDB: {str(e)}")
            return []
    
    def batch_write_records(self, records: List[Dict]) -> int:
        """
        Batch write multiple records
        
        Args:
            records: List of record dicts (must include asin, run_id, status)
            
        Returns:
            Number of records successfully written
        """
        count = 0
        
        try:
            with self.table.batch_writer() as batch:
                for record in records:
                    # Convert floats to Decimal
                    record_decimal = json.loads(json.dumps(record), parse_float=Decimal)
                    record_decimal['updated_at'] = datetime.utcnow().isoformat()
                    
                    batch.put_item(Item=record_decimal)
                    count += 1
            
            print(f"✅ Batch wrote {count} records to DynamoDB")
            return count
            
        except Exception as e:
            print(f"❌ Error batch writing to DynamoDB: {str(e)}")
            return count
    
    def get_run_summary(self, run_id: str) -> Dict:
        """
        Get summary statistics for a run
        
        Args:
            run_id: Processing run ID
            
        Returns:
            Dict with counts by status
        """
        try:
            # Scan for this run_id (inefficient for large tables, but OK for POC)
            response = self.table.scan(
                FilterExpression='run_id = :run_id',
                ExpressionAttributeValues={':run_id': run_id}
            )
            
            items = response.get('Items', [])
            
            # Count by status
            summary = {
                'total': len(items),
                'success': 0,
                'error': 0,
                'filtered': 0,
                'processing': 0
            }
            
            for item in items:
                status = item.get('status', 'unknown')
                if status in summary:
                    summary[status] += 1
            
            return summary
            
        except Exception as e:
            print(f"❌ Error getting run summary: {str(e)}")
            return {'total': 0, 'success': 0, 'error': 0, 'filtered': 0, 'processing': 0}


if __name__ == '__main__':
    # Test DynamoDB connectivity
    db_manager = DynamoDBManager(
        table_name='bedrock-ai-data-enrichment-processing-state'
    )
    
    print("="*80)
    print("Testing DynamoDB Connectivity")
    print("="*80)
    
    # Try writing a test record
    test_asin = 'TEST123'
    test_run_id = 'test-run'
    
    success = db_manager.put_record(
        asin=test_asin,
        run_id=test_run_id,
        status='processing',
        data={'test': True, 'timestamp': datetime.utcnow().isoformat()}
    )
    
    if success:
        print("✅ Successfully wrote test record")
        
        # Try reading it back
        record = db_manager.get_record(test_asin, test_run_id)
        if record:
            print(f"✅ Successfully read test record: {record}")
    else:
        print("❌ Failed to write test record")

