"""
Simple File Status Tracker
Tracks which INPUT FILES have been processed and their status

Structure:
{
  "sample_100_records.csv": {
    "status": "completed",
    "last_run_id": "run_1",
    "last_run_timestamp": "2025-12-31T19:00:00",
    "total_records": 100,
    "success": 95,
    "filtered": 3,
    "errors": 2,
    "total_cost": 0.19,
    "total_tokens": 12000,
    "input_tokens": 8000,
    "output_tokens": 4000,
    "duration_seconds": 120.5
  }
}
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


class FileTracker:
    """Simple file-level status tracking"""
    
    def __init__(self, tracking_path: str = 'data/tracking'):
        self.tracking_file = Path(tracking_path) / 'files_status.json'
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
        self.files_state = self._load()
    
    def _load(self) -> Dict:
        """Load file status"""
        if self.tracking_file.exists():
            with open(self.tracking_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save(self):
        """Save file status"""
        with open(self.tracking_file, 'w') as f:
            json.dump(self.files_state, f, indent=2, default=str)
    
    def mark_processing(self, filename: str, run_id: str, total_records: int):
        """Mark file as processing"""
        self.files_state[filename] = {
            'status': 'processing',
            'current_run_id': run_id,
            'started_at': datetime.utcnow().isoformat(),
            'total_records': total_records
        }
        self._save()
    
    def mark_completed(self, filename: str, run_id: str, success: int, filtered: int, 
                      errors: int, total_cost: float, total_tokens: int,
                      input_tokens: int, output_tokens: int, duration_seconds: float):
        """Mark file as completed"""
        self.files_state[filename] = {
            'status': 'completed',
            'last_run_id': run_id,
            'completed_at': datetime.utcnow().isoformat(),
            'total_records': success + filtered + errors,
            'success': success,
            'filtered': filtered,
            'errors': errors,
            'total_cost': total_cost,
            'total_tokens': total_tokens,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'duration_seconds': duration_seconds
        }
        self._save()
    
    def mark_error(self, filename: str, run_id: str, error_message: str):
        """Mark file as error"""
        self.files_state[filename] = {
            'status': 'error',
            'last_run_id': run_id,
            'failed_at': datetime.utcnow().isoformat(),
            'error': error_message
        }
        self._save()
    
    def get_status(self, filename: str) -> Optional[str]:
        """Get file status"""
        file_state = self.files_state.get(filename)
        return file_state.get('status') if file_state else None
    
    def get_file_info(self, filename: str) -> Optional[Dict]:
        """Get complete file info"""
        return self.files_state.get(filename)
    
    def list_all_files(self) -> Dict:
        """List all tracked files"""
        return self.files_state
    
    def can_process(self, filename: str) -> bool:
        """Check if file can be processed (not currently processing)"""
        status = self.get_status(filename)
        return status != 'processing'

