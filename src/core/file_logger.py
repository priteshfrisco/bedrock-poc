"""
Per-File Logger for AI Data Enrichment

Two-tier logging system:
1. logs/ - Lightweight step logs for terminal display
2. audit/ - Complete data lineage with step folders

Folder structure:
    data/logs/
        ├── uncoded_amz_p5_2025_subcategory_filtering.log
        ├── uncoded_amz_p5_2025_llm_classification.log
        └── uncoded_amz_p5_2025_summary.json
    
    data/audit/amz_p5_2025_20251222_103000/
        ├── step1_subcategory_filtering/
        │   ├── removed.csv
        │   └── summary.json
        ├── step2_llm_classification/
        └── run_manifest.json
"""

import os
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd


class LogLevel:
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


class FileLogger:
    
    def __init__(
        self,
        filename: str,
        run_num: int,
        mode: str = 'local',
        logs_base_path: str = 'data/logs',
        audit_base_path: str = 'data/audit',
        s3_config: Optional[Dict] = None
    ):
        self.filename = filename
        self.mode = mode
        self.file_id = self._extract_file_id(filename)
        self.run_num = run_num
        self.run_id = f"run_{run_num}"
        
        if mode == 'local':
            self._setup_local(logs_base_path, audit_base_path)
        else:
            self._setup_s3(s3_config)
    
    def _setup_local(self, logs_base_path: str, audit_base_path: str):
        self.logs_path = Path(logs_base_path) / self.file_id / self.run_id
        self.audit_path = Path(audit_base_path) / self.file_id / self.run_id
        
        self.logs_path.mkdir(parents=True, exist_ok=True)
        self.audit_path.mkdir(parents=True, exist_ok=True)
        
        self.s3_client = None
        self.s3_bucket = None
    
    def _setup_s3(self, s3_config: Optional[Dict]):
        if not s3_config:
            raise ValueError("s3_config required for AWS mode")
        
        import boto3
        from botocore.exceptions import NoCredentialsError
        
        self.s3_logs_bucket = s3_config.get('logs_bucket')
        self.s3_audit_bucket = s3_config.get('audit_bucket', self.s3_logs_bucket)
        
        if not self.s3_logs_bucket:
            raise ValueError("logs_bucket required in s3_config")
        
        region = s3_config.get('region', 'us-east-2')
        
        try:
            self.s3_client = boto3.client('s3', region_name=region)
        except NoCredentialsError:
            raise ValueError("AWS credentials not found")
        
        self.s3_logs_prefix = f"logs/"
        self.s3_audit_prefix = f"audit/{self.run_id}/"
        
        self.logs_path = Path('/tmp') / 'logs'
        self.audit_path = Path('/tmp') / 'audit' / self.run_id
        self.logs_path.mkdir(parents=True, exist_ok=True)
        self.audit_path.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def _extract_file_id(filename: str) -> str:
        name = Path(filename).stem
        if name.startswith('uncoded_'):
            name = name[8:]
        return name
    
    def get_step_log_path(self, step_name: str) -> Path:
        return self.logs_path / f"{step_name}.log"
    
    def get_step_audit_path(self, step_name: str) -> Path:
        step_folder = self.audit_path / step_name
        step_folder.mkdir(parents=True, exist_ok=True)
        return step_folder
    
    def log_step(self, step_name: str, message: str, level: str = LogLevel.INFO):
        timestamp = datetime.utcnow().isoformat()
        log_entry = f"[{timestamp}] {level}: {message}\n"
        
        log_file = self.get_step_log_path(step_name)
        self._append_to_file(log_file, log_entry)
        
        if self.mode == 'aws':
            self._upload_to_s3(log_file, f"{step_name}.log")
    
    def write_step_csv(
        self,
        step_name: str,
        df: pd.DataFrame,
        csv_name: str
    ):
        step_folder = self.get_step_audit_path(step_name)
        csv_path = step_folder / csv_name
        
        df.to_csv(csv_path, index=False, encoding='utf-8')
        
        if self.mode == 'aws':
            self._upload_to_s3(csv_path, f"{step_name}/{csv_name}")
    
    def write_step_summary(
        self,
        step_name: str,
        summary_data: Dict[str, Any]
    ):
        step_folder = self.get_step_audit_path(step_name)
        summary_path = step_folder / 'summary.json'
        
        summary_data['generated_at'] = datetime.utcnow().isoformat()
        summary_data['step'] = step_name
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2)
        
        if self.mode == 'aws':
            self._upload_to_s3(summary_path, f"{step_name}/summary.json")
    
    def write_final_summary(self, summary_data: Dict[str, Any]):
        summary_data['generated_at'] = datetime.utcnow().isoformat()
        summary_data['filename'] = self.filename
        summary_data['file_id'] = self.file_id
        summary_data['run_id'] = self.run_id
        summary_data['run_num'] = self.run_num
        
        manifest_path = self.audit_path / 'run_manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2)
        
        if self.mode == 'aws':
            self._upload_to_s3(manifest_path, f"run_manifest.json")
    
    def _append_to_file(self, filepath: Path, content: str):
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(content)
    
    def _upload_to_s3(self, local_path: Path, s3_key: str):
        if not self.s3_client:
            return
        
        try:
            bucket = self.s3_audit_bucket if 'step' in s3_key or 'manifest' in s3_key else self.s3_logs_bucket
            full_key = f"{self.s3_audit_prefix if 'step' in s3_key else self.s3_logs_prefix}{s3_key}"
            
            self.s3_client.upload_file(
                str(local_path),
                bucket,
                full_key
            )
        except Exception as e:
            print(f"Warning: Failed to upload {s3_key} to S3: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.mode == 'aws':
            self._upload_all_to_s3()
    
    def _upload_all_to_s3(self):
        pass
    
    def get_logs_path(self) -> Path:
        return self.logs_path
    
    def get_audit_path(self) -> Path:
        return self.audit_path
    
    def get_info(self) -> Dict[str, str]:
        return {
            'filename': self.filename,
            'file_id': self.file_id,
            'run_id': self.run_id,
            'run_num': self.run_num,
            'mode': self.mode,
            'logs_path': str(self.logs_path),
            'audit_path': str(self.audit_path)
        }


def get_next_run_number(filename: str, base_path: str = 'data/audit') -> int:
    file_id = FileLogger._extract_file_id(filename)
    audit_path = Path(base_path) / file_id
    
    if not audit_path.exists():
        return 1
    
    existing_runs = [d.name for d in audit_path.iterdir() if d.is_dir() and d.name.startswith('run_')]
    if not existing_runs:
        return 1
    
    run_numbers = [int(r.split('_')[1]) for r in existing_runs]
    return max(run_numbers) + 1


def create_file_logger(
    filename: str,
    run_num: Optional[int] = None,
    mode: Optional[str] = None,
    logs_base_path: str = 'data/logs',
    audit_base_path: str = 'data/audit',
    s3_config: Optional[Dict] = None
) -> FileLogger:
    if mode is None:
        mode = os.getenv('STORAGE_MODE', 'local')
    
    if run_num is None:
        run_num = get_next_run_number(filename, audit_base_path)
    
    return FileLogger(
        filename=filename,
        run_num=run_num,
        mode=mode,
        logs_base_path=logs_base_path,
        audit_base_path=audit_base_path,
        s3_config=s3_config
    )

