"""
Centralized Log Manager - Controls ALL logging and audit file creation

This is the ONLY place that decides:
- Where logs go
- Where audit files go
- Folder structure
- File naming conventions
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import pandas as pd

from src.core.file_utils import write_csv, write_log, ensure_dir


class LogManager:
    """Centralized logging controller"""
    
    def __init__(self, input_filename: str, base_path: str = 'data'):
        self.input_filename = input_filename
        self.base_path = Path(base_path)
        
        # Extract file_id from filename (remove 'uncoded_' prefix if present)
        self.file_id = self._extract_file_id(input_filename)
        
        # Get next run number
        self.run_num = self._get_next_run_number()
        self.run_id = f"run_{self.run_num}"
        
        # Define paths
        self.logs_path = self.base_path / 'logs' / self.file_id / self.run_id
        self.audit_path = self.base_path / 'audit' / self.file_id / self.run_id
        
        # Create base directories
        ensure_dir(self.logs_path)
        ensure_dir(self.audit_path)
        
        # Log start
        self._log_run_start()
    
    def _extract_file_id(self, filename: str) -> str:
        """Extract clean file ID from filename"""
        name = Path(filename).stem
        if name.startswith('uncoded_'):
            name = name[8:]
        return name
    
    def _get_next_run_number(self) -> int:
        """Determine next run number for this file"""
        file_audit_path = self.base_path / 'audit' / self.file_id
        
        if not file_audit_path.exists():
            return 1
        
        existing_runs = [
            d.name for d in file_audit_path.iterdir() 
            if d.is_dir() and d.name.startswith('run_')
        ]
        
        if not existing_runs:
            return 1
        
        run_numbers = [int(r.split('_')[1]) for r in existing_runs]
        return max(run_numbers) + 1
    
    def _log_run_start(self):
        """Log run initialization"""
        timestamp = datetime.utcnow().isoformat()
        message = f"[{timestamp}] RUN START: {self.input_filename} | Run: {self.run_id}"
        write_log(self.logs_path / 'run.log', message)
    
    # ========== STEP LOGGING ==========
    
    def log_step(self, step_name: str, message: str):
        """Log a message for a specific step"""
        timestamp = datetime.utcnow().isoformat()
        log_message = f"[{timestamp}] {message}"
        
        step_log_file = self.logs_path / f"{step_name}.log"
        write_log(step_log_file, log_message)
    
    def log_step_start(self, step_name: str, step_title: str):
        """Log start of a step"""
        self.log_step(step_name, "="*60)
        self.log_step(step_name, f"{step_title}")
        self.log_step(step_name, "="*60)
    
    def log_step_end(self, step_name: str):
        """Log end of a step"""
        self.log_step(step_name, "="*60)
        self.log_step(step_name, "")
    
    # ========== AUDIT FILES ==========
    
    def save_audit_csv(self, step_name: str, df: pd.DataFrame, filename: str):
        """Save audit CSV for a step"""
        step_audit_path = self.audit_path / step_name
        ensure_dir(step_audit_path)
        
        csv_path = step_audit_path / filename
        write_csv(csv_path, df)
        
        # Log what was saved
        relative_path = f"audit/{self.file_id}/{self.run_id}/{step_name}/{filename}"
        self.log_step(step_name, f"Saved: {relative_path} ({len(df):,} rows)")
        
        return csv_path
    
    def save_audit_json(self, step_name: str, data: Dict[str, Any], filename: str):
        """Save audit JSON for a step"""
        step_audit_path = self.audit_path / step_name
        ensure_dir(step_audit_path)
        
        json_path = step_audit_path / filename
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        # Log what was saved
        relative_path = f"audit/{self.file_id}/{self.run_id}/{step_name}/{filename}"
        self.log_step(step_name, f"Saved: {relative_path}")
        
        return json_path
    
    # ========== RUN SUMMARY ==========
    
    def save_run_manifest(self, summary_data: Dict[str, Any]):
        """Save final run manifest"""
        summary_data['generated_at'] = datetime.utcnow().isoformat()
        summary_data['filename'] = self.input_filename
        summary_data['file_id'] = self.file_id
        summary_data['run_id'] = self.run_id
        summary_data['run_num'] = self.run_num
        
        manifest_path = self.audit_path / 'run_manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2)
        
        self.log_step('run', f"Run manifest saved: audit/{self.file_id}/{self.run_id}/run_manifest.json")
    
    # ========== INFO ==========
    
    def get_info(self) -> Dict[str, str]:
        """Get logging information"""
        return {
            'filename': self.input_filename,
            'file_id': self.file_id,
            'run_id': self.run_id,
            'run_num': self.run_num,
            'logs_path': str(self.logs_path),
            'audit_path': str(self.audit_path)
        }

