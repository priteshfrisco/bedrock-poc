"""
Database Manager for Production Tracking
Supports SQLite (local) and PostgreSQL (AWS production)
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import contextmanager


class DBManager:
    """Database manager for tracking file and product processing status"""
    
    def __init__(self, db_path: str = 'data/tracking/processing.db', db_type: str = 'sqlite'):
        self.db_path = db_path
        self.db_type = db_type
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        if self.db_type == 'sqlite':
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        else:
            # TODO: Add PostgreSQL support for AWS
            raise NotImplementedError("PostgreSQL support coming soon")
    
    def _init_db(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # File-level tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_processing (
                    file_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    run_id TEXT,
                    total_records INTEGER,
                    processed_records INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    filtered_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    last_heartbeat TIMESTAMP,
                    worker_id TEXT,
                    total_cost REAL DEFAULT 0.0,
                    total_tokens INTEGER DEFAULT 0
                )
            """)
            
            # Product-level tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_processing (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL,
                    run_id TEXT,
                    product_id INTEGER,
                    asin TEXT,
                    title TEXT,
                    brand TEXT,
                    status TEXT NOT NULL,
                    step_completed INTEGER DEFAULT 0,
                    filter_reason TEXT,
                    category TEXT,
                    subcategory TEXT,
                    primary_ingredient TEXT,
                    error_message TEXT,
                    tokens_used INTEGER DEFAULT 0,
                    api_cost REAL DEFAULT 0.0,
                    processing_time_sec REAL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    worker_id TEXT,
                    FOREIGN KEY (file_id) REFERENCES file_processing(file_id)
                )
            """)
            
            # Create indexes for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_status 
                ON product_processing(file_id, status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_asin 
                ON product_processing(asin)
            """)
            
            conn.commit()
    
    # ========== FILE TRACKING ==========
    
    def start_file_processing(self, file_id: str, filename: str, run_id: str, 
                             total_records: int, worker_id: str = 'worker_1'):
        """Mark file as processing"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO file_processing 
                (file_id, filename, status, run_id, total_records, started_at, last_heartbeat, worker_id)
                VALUES (?, ?, 'processing', ?, ?, ?, ?, ?)
            """, (file_id, filename, run_id, total_records, 
                  datetime.utcnow(), datetime.utcnow(), worker_id))
    
    def update_file_heartbeat(self, file_id: str):
        """Update heartbeat to show file is still being processed"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE file_processing 
                SET last_heartbeat = ?
                WHERE file_id = ?
            """, (datetime.utcnow(), file_id))
    
    def complete_file_processing(self, file_id: str, success: int, filtered: int, 
                                 errors: int, total_cost: float, total_tokens: int):
        """Mark file as completed"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE file_processing 
                SET status='completed', completed_at=?, 
                    processed_records=?, success_count=?, filtered_count=?, 
                    error_count=?, total_cost=?, total_tokens=?
                WHERE file_id=?
            """, (datetime.utcnow(), success+filtered+errors, success, filtered, 
                  errors, total_cost, total_tokens, file_id))
    
    def get_file_status(self, file_id: str) -> Optional[Dict]:
        """Get file processing status"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM file_processing WHERE file_id=?
            """, (file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def find_crashed_files(self, timeout_minutes: int = 5) -> List[Dict]:
        """Find files that appear to have crashed (no heartbeat for N minutes)"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM file_processing 
                WHERE status='processing'
                  AND datetime(last_heartbeat) < datetime('now', '-' || ? || ' minutes')
            """, (timeout_minutes,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== PRODUCT TRACKING ==========
    
    def init_products(self, file_id: str, run_id: str, products: List[Dict]):
        """Initialize all products for a file as 'pending'"""
        with self.get_connection() as conn:
            for product in products:
                conn.execute("""
                    INSERT INTO product_processing 
                    (file_id, run_id, product_id, asin, title, brand, status, started_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """, (file_id, run_id, product['product_id'], product['asin'],
                      product['title'], product['brand'], datetime.utcnow()))
    
    def start_product_processing(self, asin: str, worker_id: str = 'worker_1'):
        """Mark product as processing"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE product_processing 
                SET status='processing', worker_id=?, started_at=?
                WHERE asin=?
            """, (worker_id, datetime.utcnow(), asin))
    
    def update_product_status(self, asin: str, status: str, step_completed: int,
                             **kwargs):
        """Update product processing status"""
        # Build dynamic UPDATE query
        update_fields = ['status=?', 'step_completed=?']
        values = [status, step_completed]
        
        for key, value in kwargs.items():
            update_fields.append(f'{key}=?')
            values.append(value)
        
        values.append(asin)  # WHERE asin=?
        
        query = f"""
            UPDATE product_processing 
            SET {', '.join(update_fields)}
            WHERE asin=?
        """
        
        with self.get_connection() as conn:
            conn.execute(query, values)
    
    def get_product_status(self, asin: str) -> Optional[Dict]:
        """Get product processing status"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM product_processing WHERE asin=?
            """, (asin,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_pending_products(self, file_id: str) -> List[Dict]:
        """Get all pending products for a file (for resume)"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM product_processing 
                WHERE file_id=? AND status='pending'
                ORDER BY product_id
            """, (file_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_crashed_products(self, file_id: str, timeout_minutes: int = 5) -> List[Dict]:
        """Get products that appear to have crashed (status='processing' but old timestamp)"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM product_processing 
                WHERE file_id=? 
                  AND status='processing'
                  AND datetime(started_at) < datetime('now', '-' || ? || ' minutes')
                ORDER BY product_id
            """, (file_id, timeout_minutes))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_file_progress(self, file_id: str) -> Dict:
        """Get detailed progress for a file"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    status,
                    COUNT(*) as count
                FROM product_processing
                WHERE file_id=?
                GROUP BY status
            """, (file_id,))
            
            progress = {row['status']: row['count'] for row in cursor.fetchall()}
            return progress
    
    def can_process_file(self, file_id: str) -> bool:
        """Check if file can be processed (not currently processing)"""
        file_status = self.get_file_status(file_id)
        if not file_status:
            return True  # New file
        
        # Allow if completed or if crashed (no heartbeat in 5 minutes)
        if file_status['status'] == 'completed':
            return False
        
        if file_status['status'] == 'processing':
            # Check if crashed
            last_heartbeat = datetime.fromisoformat(file_status['last_heartbeat'])
            if (datetime.utcnow() - last_heartbeat).seconds > 300:  # 5 minutes
                return True  # Crashed, can resume
            return False  # Still processing
        
        return True

