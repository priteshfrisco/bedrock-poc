"""
Data Preprocessing - Standardize raw CSV data + Non-Supplement Filtering
"""

import pandas as pd
import csv
from typing import Dict, List, Tuple


COLUMN_MAPPING = {
    'ASIN/UPC Key': 'asin',
    'MI: Brand': 'brand',
    'MI: Description': 'title',
    'Source Subcategory Trx': 'amazon_subcategory'
}

REQUIRED_COLUMNS = ['asin', 'brand', 'title', 'amazon_subcategory']


# Load non-supplement keywords
def load_non_supplement_keywords() -> List[str]:
    """Load non-supplement keywords from CSV"""
    keywords = []
    try:
        with open('reference_data/non_supplement_keywords.csv', 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                keyword = row.get('keyword', '').strip().lower()
                if keyword:
                    keywords.append(keyword)
    except FileNotFoundError:
        # Fallback to hardcoded list
        keywords = [
            'book', 'shirt', 'bottle', 'shaker', 'cup', 'bag', 'container',
            'pillbox', 'organizer', 'test kit', 'equipment', 'scale', 'mixer',
            'blender', 'clothing', 'apparel', 'accessory', 'thermometer'
        ]
    return keywords


_NON_SUPPLEMENT_KEYWORDS = None


def is_non_supplement(title: str) -> Tuple[bool, str]:
    """
    Check if a product title contains non-supplement keywords
    
    Args:
        title: Product title
    
    Returns:
        Tuple of (is_non_supplement, reason)
    """
    global _NON_SUPPLEMENT_KEYWORDS
    
    if _NON_SUPPLEMENT_KEYWORDS is None:
        _NON_SUPPLEMENT_KEYWORDS = load_non_supplement_keywords()
    
    if not title or not isinstance(title, str):
        return False, "Empty or invalid title"
    
    title_lower = title.lower()
    
    for keyword in _NON_SUPPLEMENT_KEYWORDS:
        if keyword in title_lower:
            return True, f"Contains non-supplement keyword: '{keyword}'"
    
    return False, "No non-supplement keywords found"


def standardize_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize raw DataFrame:
    1. Rename columns
    2. Convert to lowercase
    3. Clean whitespace
    4. Validate required columns exist
    """
    
    if raw_df.empty:
        return raw_df.copy()
    
    # Validate input columns
    _validate_input_columns(raw_df)
    
    df = raw_df.copy()
    
    # Rename columns
    df = df.rename(columns=COLUMN_MAPPING)
    
    # Convert text columns to lowercase
    text_columns = ['brand', 'title', 'amazon_subcategory']
    for col in text_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().str.strip()
    
    # Validate output
    _validate_output_columns(df)
    
    return df


def _validate_input_columns(df: pd.DataFrame):
    """Validate that required input columns exist"""
    missing = [col for col in COLUMN_MAPPING.keys() if col not in df.columns]
    
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}\n"
            f"Expected: {list(COLUMN_MAPPING.keys())}\n"
            f"Found: {list(df.columns)}"
        )


def _validate_output_columns(df: pd.DataFrame):
    """Validate that required output columns exist"""
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    
    if missing:
        raise ValueError(f"Preprocessing failed: missing columns {missing}")

