"""
Data Preprocessing - Standardize raw CSV data + Non-Supplement Filtering
"""

import pandas as pd
import csv
import re
from typing import Dict, List, Tuple


COLUMN_MAPPING = {
    'ASIN/UPC Key': 'asin',
    'MI: Brand': 'brand',
    'MI: Description': 'title',
    'Source Subcategory Trx': 'amazon_subcategory'
}

REQUIRED_COLUMNS = ['asin', 'brand', 'title', 'amazon_subcategory']


# Load non-supplement keywords with variations and exceptions
def load_non_supplement_keywords() -> List[Dict]:
    """
    Load non-supplement keywords from CSV with auto_variations and exceptions
    
    Returns:
        List of dicts with 'keyword', 'variations', 'exceptions'
    """
    keywords = []
    try:
        with open('reference_data/non_supplement_keywords.csv', 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                keyword = row.get('keyword', '').strip().lower()
                if not keyword:
                    continue
                
                # Check if auto_variations is enabled
                auto_var = row.get('auto_variations', '').strip().lower()
                
                # Generate variations if enabled
                variations = [keyword]
                if auto_var == 'yes':
                    variations.extend(generate_keyword_variations(keyword))
                
                # Parse exceptions (comma-separated)
                exceptions_str = row.get('exceptions', '').strip().lower()
                exceptions = []
                if exceptions_str:
                    exceptions = [e.strip() for e in exceptions_str.split(',') if e.strip()]
                
                keywords.append({
                    'keyword': keyword,
                    'variations': variations,
                    'exceptions': exceptions
                })
    except FileNotFoundError:
        # Fallback to hardcoded list
        keywords = [
            {'keyword': 'book', 'variations': ['book', 'books', 'ebook', 'e-book'], 'exceptions': []},
            {'keyword': 'shirt', 'variations': ['shirt', 'shirts', 't-shirt', 't shirt'], 'exceptions': []},
            {'keyword': 'bottle', 'variations': ['bottle'], 'exceptions': []},
            {'keyword': 'shaker', 'variations': ['shaker'], 'exceptions': []},
            {'keyword': 'test kit', 'variations': ['test kit'], 'exceptions': []},
        ]
    return keywords


def generate_keyword_variations(keyword: str) -> List[str]:
    """
    Generate common variations of a keyword
    
    Examples:
    - 'book' -> ['books', 'ebook', 'e-book', 'e book']
    - 'jewelry' -> ['jewelries', 'jewellery', 'jewelleries']
    - 'lotion' -> ['lotions']
    """
    variations = []
    
    # Add plural (simple 's' ending)
    if not keyword.endswith('s'):
        variations.append(keyword + 's')
    
    # Add 'e-' prefix variations (e-book, ebook, e book)
    if ' ' in keyword:
        # Multi-word: "test kit" -> no e- prefix
        pass
    else:
        # Single word
        variations.append(f'e-{keyword}')
        variations.append(f'e{keyword}')
        variations.append(f'e {keyword}')
    
    # Add hyphen variations if keyword has spaces
    if ' ' in keyword:
        variations.append(keyword.replace(' ', '-'))
        variations.append(keyword.replace(' ', ''))
    
    # Add space variations if keyword has hyphens
    if '-' in keyword:
        variations.append(keyword.replace('-', ' '))
        variations.append(keyword.replace('-', ''))
    
    return variations


_NON_SUPPLEMENT_KEYWORDS = None


def is_non_supplement(title: str) -> Tuple[bool, str]:
    """
    Check if a product title contains non-supplement keywords
    
    Supports:
    - auto_variations: Automatically generates common variations (plural, e-prefix, hyphen/space)
    - exceptions: If title contains exception keywords, don't filter
    - Word boundaries: Only matches whole words (e.g. 'book' won't match 'notebook')
    
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
    
    for keyword_data in _NON_SUPPLEMENT_KEYWORDS:
        variations = keyword_data['variations']
        exceptions = keyword_data['exceptions']
        base_keyword = keyword_data['keyword']
        
        # Check if any variation matches (using word boundaries)
        for variation in variations:
            # Use word boundary regex for whole word matching
            # \b matches word boundaries (space, hyphen, start/end of string, etc.)
            pattern = r'\b' + re.escape(variation) + r'\b'
            
            if re.search(pattern, title_lower):
                # Check exceptions - if any exception word is in title, skip filtering
                # Use substring matching for exceptions (more flexible - handles plural, etc.)
                has_exception = False
                for exception in exceptions:
                    if exception in title_lower:
                        has_exception = True
                        break
                
                if has_exception:
                    # Don't filter - exception applies
                    continue
                
                # Filter this product
                return True, f"Contains non-supplement keyword: '{base_keyword}'"
    
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

