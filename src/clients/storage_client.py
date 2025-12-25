"""
Storage Client - Unified interface for file operations

Supports two modes:
- LOCAL: Uses local filesystem (data/input, data/output)
- AWS: Uses S3 buckets
"""

import os
from pathlib import Path
from typing import List, Dict, Optional
import pandas as pd

# Try to import boto3
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


class StorageClient:
    """
    Abstraction layer for file storage operations
    
    Usage:
        # Local mode (development/testing)
        storage = StorageClient(mode='local')
        
        # AWS mode (production)
        storage = StorageClient(
            mode='aws',
            s3_config={
                'input_bucket': 'bucket-name',
                'output_bucket': 'bucket-name',
                'region': 'us-east-2'
            }
        )
    """
    
    def __init__(
        self,
        mode: str = 'local',
        base_path: str = 'data',
        s3_config: Optional[Dict[str, str]] = None
    ):
        """
        Initialize storage client
        
        Args:
            mode: 'local' or 'aws'
            base_path: Base directory for local mode (default: 'data')
            s3_config: Configuration for AWS mode with keys:
                - input_bucket: S3 bucket for input files
                - output_bucket: S3 bucket for output files
                - region: AWS region (default: us-east-2)
        
        Raises:
            ValueError: If mode is invalid or required config missing
            ImportError: If AWS mode requested but boto3 not installed
        """
        self.mode = mode.lower()
        
        if self.mode not in ['local', 'aws']:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'local' or 'aws'")
        
        if self.mode == 'local':
            self._init_local(base_path)
        elif self.mode == 'aws':
            self._init_aws(s3_config)
    
    def _init_local(self, base_path: str):
        """Initialize local filesystem storage"""
        self.base_path = Path(base_path)
        self.input_dir = self.base_path / 'input'
        self.output_dir = self.base_path / 'output'
        
        # Create directories if they don't exist
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_aws(self, s3_config: Optional[Dict[str, str]]):
        """Initialize AWS S3 storage"""
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 is required for AWS mode. "
                "Install with: pip install boto3"
            )
        
        if not s3_config:
            raise ValueError("s3_config is required for AWS mode")
        
        required_keys = ['input_bucket', 'output_bucket']
        missing_keys = [k for k in required_keys if k not in s3_config]
        if missing_keys:
            raise ValueError(
                f"Missing required s3_config keys: {missing_keys}"
            )
        
        self.input_bucket = s3_config['input_bucket']
        self.output_bucket = s3_config['output_bucket']
        self.region = s3_config.get('region', 'us-east-2')
        
        # Initialize S3 client
        try:
            self.s3_client = boto3.client('s3', region_name=self.region)
        except NoCredentialsError:
            raise ValueError(
                "AWS credentials not found. "
                "Configure with: aws configure"
            )
    
    # ========================================================================
    # LIST FILES
    # ========================================================================
    
    def list_input_files(self, pattern: str = '*.csv') -> List[str]:
        """
        List files in input location
        
        Args:
            pattern: File pattern to match (default: '*.csv')
        
        Returns:
            List of filenames (not full paths)
        """
        if self.mode == 'local':
            return self._list_local_files(self.input_dir, pattern)
        else:
            return self._list_s3_files(self.input_bucket, 'input/', pattern)
    
    def _list_local_files(self, directory: Path, pattern: str) -> List[str]:
        """List files in local directory"""
        files = list(directory.glob(pattern))
        return [f.name for f in files if f.is_file()]
    
    def _list_s3_files(
        self,
        bucket: str,
        prefix: str,
        pattern: str
    ) -> List[str]:
        """List files in S3 bucket"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                return []
            
            # Extract filenames and filter by pattern
            files = []
            suffix = pattern.replace('*', '')
            
            for obj in response['Contents']:
                key = obj['Key']
                filename = key.split('/')[-1]
                
                # Skip empty filenames (directories)
                if not filename:
                    continue
                
                # Filter by pattern
                if filename.endswith(suffix):
                    files.append(filename)
            
            return files
            
        except ClientError as e:
            raise IOError(f"Failed to list S3 files: {e}")
    
    # ========================================================================
    # READ FILES
    # ========================================================================
    
    def read_csv(self, filename: str) -> pd.DataFrame:
        """
        Read CSV file from input location
        
        Args:
            filename: Name of the CSV file
        
        Returns:
            pandas DataFrame
        
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file cannot be read as CSV
        """
        if self.mode == 'local':
            return self._read_local_csv(filename)
        else:
            return self._read_s3_csv(filename)
    
    def _read_local_csv(self, filename: str) -> pd.DataFrame:
        """Read CSV from local filesystem"""
        filepath = self.input_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(
                f"File not found: {filepath}"
            )
        
        # Try multiple encodings
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        
        for encoding in encodings:
            try:
                return pd.read_csv(filepath, encoding=encoding)
            except UnicodeDecodeError:
                continue
        
        raise ValueError(
            f"Failed to read {filename} with any encoding. "
            f"Tried: {encodings}"
        )
    
    def _read_s3_csv(self, filename: str) -> pd.DataFrame:
        """Read CSV from S3"""
        s3_key = f'input/{filename}'
        
        try:
            obj = self.s3_client.get_object(
                Bucket=self.input_bucket,
                Key=s3_key
            )
            
            # Try multiple encodings
            encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
            
            for encoding in encodings:
                try:
                    return pd.read_csv(obj['Body'], encoding=encoding)
                except UnicodeDecodeError:
                    # Reset stream for next attempt
                    obj['Body'].seek(0)
                    continue
            
            raise ValueError(
                f"Failed to read {filename} from S3 with any encoding"
            )
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(
                    f"File not found in S3: {s3_key}"
                )
            else:
                raise IOError(f"Failed to read from S3: {e}")
    
    # ========================================================================
    # WRITE FILES
    # ========================================================================
    
    def write_csv(
        self,
        df: pd.DataFrame,
        filename: str,
        subfolder: str = ''
    ) -> str:
        """
        Write DataFrame to CSV in output location
        
        Args:
            df: pandas DataFrame to write
            filename: Output filename (e.g., 'coded_products.csv')
            subfolder: Optional subfolder (e.g., 'review_queue/')
        
        Returns:
            Full path or S3 URI where file was written
        """
        if self.mode == 'local':
            return self._write_local_csv(df, filename, subfolder)
        else:
            return self._write_s3_csv(df, filename, subfolder)
    
    def _write_local_csv(
        self,
        df: pd.DataFrame,
        filename: str,
        subfolder: str
    ) -> str:
        """Write CSV to local filesystem"""
        output_path = self.output_dir / subfolder / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        df.to_csv(output_path, index=False, encoding='utf-8')
        
        return str(output_path)
    
    def _write_s3_csv(
        self,
        df: pd.DataFrame,
        filename: str,
        subfolder: str
    ) -> str:
        """Write CSV to S3"""
        s3_key = f'output/{subfolder}{filename}'
        
        # Convert DataFrame to CSV string
        csv_buffer = df.to_csv(index=False, encoding='utf-8')
        
        try:
            self.s3_client.put_object(
                Bucket=self.output_bucket,
                Key=s3_key,
                Body=csv_buffer.encode('utf-8'),
                ContentType='text/csv'
            )
            
            return f's3://{self.output_bucket}/{s3_key}'
            
        except ClientError as e:
            raise IOError(f"Failed to write to S3: {e}")
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def get_info(self) -> Dict[str, str]:
        """Get information about storage configuration"""
        if self.mode == 'local':
            return {
                'mode': 'local',
                'base_path': str(self.base_path),
                'input_dir': str(self.input_dir),
                'output_dir': str(self.output_dir)
            }
        else:
            return {
                'mode': 'aws',
                'region': self.region,
                'input_bucket': self.input_bucket,
                'output_bucket': self.output_bucket
            }


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_storage_client_from_env() -> StorageClient:
    """
    Create storage client from environment variables
    
    Environment variables:
        STORAGE_MODE: 'local' or 'aws' (default: 'local')
        
        For local mode:
        - DATA_PATH: Base directory (default: 'data')
        
        For AWS mode:
        - S3_INPUT_BUCKET: S3 bucket for input files (required)
        - S3_OUTPUT_BUCKET: S3 bucket for output files (required)
        - AWS_REGION: AWS region (default: 'us-east-2')
    
    Returns:
        Configured StorageClient instance
    """
    mode = os.getenv('STORAGE_MODE', 'local')
    
    if mode == 'aws':
        s3_config = {
            'input_bucket': os.getenv('S3_INPUT_BUCKET'),
            'output_bucket': os.getenv('S3_OUTPUT_BUCKET'),
            'region': os.getenv('AWS_REGION', 'us-east-2')
        }
        
        # Validate required env vars
        if not s3_config['input_bucket']:
            raise ValueError("S3_INPUT_BUCKET environment variable required for AWS mode")
        if not s3_config['output_bucket']:
            raise ValueError("S3_OUTPUT_BUCKET environment variable required for AWS mode")
        
        return StorageClient(mode='aws', s3_config=s3_config)
    
    else:
        base_path = os.getenv('DATA_PATH', 'data')
        return StorageClient(mode='local', base_path=base_path)


# ============================================================================
# MAIN - For testing
# ============================================================================

if __name__ == "__main__":
    import sys
    
    print("Storage Client Test")
    print("=" * 50)
    
    # Test local mode
    print("\n1. Testing LOCAL mode...")
    try:
        storage = StorageClient(mode='local')
        info = storage.get_info()
        print(f"   Mode: {info['mode']}")
        print(f"   Input dir: {info['input_dir']}")
        print(f"   Output dir: {info['output_dir']}")
        
        files = storage.list_input_files()
        print(f"   Found {len(files)} input files: {files}")
        
        print("   ✅ Local mode OK")
    except Exception as e:
        print(f"   ❌ Local mode failed: {e}")
        sys.exit(1)
    
    print("\n✅ Storage client tests passed!")

