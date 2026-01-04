"""
Simple file I/O utilities - No business logic, just read/write
"""

import pandas as pd
from pathlib import Path
from typing import Union


def write_csv(filepath: Union[str, Path], df: pd.DataFrame):
    """Write DataFrame to CSV"""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False, encoding='utf-8')


def read_csv(filepath: Union[str, Path]) -> pd.DataFrame:
    """Read CSV into DataFrame"""
    # Try different encodings
    for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
        try:
            return pd.read_csv(filepath, encoding=encoding)
        except UnicodeDecodeError:
            continue
    # If all fail, try with errors='ignore'
    return pd.read_csv(filepath, encoding='utf-8', errors='ignore')


def write_log(filepath: Union[str, Path], message: str):
    """Append message to log file"""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(message + '\n')


def ensure_dir(dirpath: Union[str, Path]):
    """Create directory if it doesn't exist"""
    Path(dirpath).mkdir(parents=True, exist_ok=True)

