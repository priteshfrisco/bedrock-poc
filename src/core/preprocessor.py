"""
Standardizes raw CSV data for processing pipeline.
Handles column renaming, lowercase conversion, and validation.
"""

from typing import Dict, List
import pandas as pd


class DataPreprocessor:
    
    COLUMN_MAPPING = {
        'ASIN/UPC Key': 'asin',
        'MI: Brand': 'brand',
        'MI: Description': 'title',
        'Source Subcategory Trx': 'amazon_subcategory'
    }
    
    REQUIRED_COLUMNS = ['asin', 'brand', 'title', 'amazon_subcategory']
    
    def __init__(self):
        self.processed_count = 0
        self.errors = []
    
    def standardize(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        if raw_df.empty:
            return raw_df.copy()
        
        self._validate_input_columns(raw_df)
        
        df = raw_df.copy()
        df = self._rename_columns(df)
        df = self._convert_to_lowercase(df)
        df = self._clean_whitespace(df)
        
        self._validate_output(df)
        self.processed_count = len(df)
        
        return df
    
    def _validate_input_columns(self, df: pd.DataFrame):
        missing_columns = [col for col in self.COLUMN_MAPPING.keys() if col not in df.columns]
        
        if missing_columns:
            raise ValueError(
                f"Missing required columns: {missing_columns}\n"
                f"Expected: {list(self.COLUMN_MAPPING.keys())}\n"
                f"Found: {list(df.columns)}"
            )
    
    def _rename_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.rename(columns=self.COLUMN_MAPPING)
    
    def _convert_to_lowercase(self, df: pd.DataFrame) -> pd.DataFrame:
        text_columns = ['brand', 'title', 'amazon_subcategory']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.lower()
        return df
    
    def _clean_whitespace(self, df: pd.DataFrame) -> pd.DataFrame:
        text_columns = ['brand', 'title', 'amazon_subcategory']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].str.strip()
        return df
    
    def _validate_output(self, df: pd.DataFrame):
        missing_columns = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Preprocessing failed: missing columns {missing_columns}")
    
    def get_stats(self) -> Dict:
        return {
            'processed_count': self.processed_count,
            'errors': len(self.errors)
        }


def standardize_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    preprocessor = DataPreprocessor()
    return preprocessor.standardize(raw_df)


def get_column_mapping() -> Dict[str, str]:
    return DataPreprocessor.COLUMN_MAPPING.copy()


def get_required_columns() -> List[str]:
    return list(DataPreprocessor.COLUMN_MAPPING.keys())

