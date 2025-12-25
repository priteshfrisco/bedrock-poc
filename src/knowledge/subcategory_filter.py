"""
Filters out non-supplement products based on Amazon subcategory and title keywords.
First step in classification pipeline - removes non-supplements before LLM.

Two-stage filtering:
1. Subcategory lookup (checks Amazon category field)
2. Title keyword filtering (catches what subcategory missed - automates manual cleanup)
"""

import json
import re
import csv
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd


class SubcategoryFilter:
    
    def __init__(
        self,
        lookup_file: str = 'reference_data/amazon_subcategory_lookup.csv',
        keywords_file: str = 'reference_data/non_supplement_keywords.csv'
    ):
        self.lookup_file = Path(lookup_file)
        self.keywords_file = Path(keywords_file)
        self.lookup = self._load_lookup()
        self.keywords_data = self._load_keywords()
        self.non_supplement_patterns = self._generate_patterns()
        self.pattern_exceptions = self._extract_exceptions()
        self.total_processed = 0
        self.total_removed = 0
        self.total_remapped = 0
        self.total_not_found = 0
        self.total_removed_by_subcategory = 0
        self.total_removed_by_title = 0
    
    def _load_lookup(self) -> Dict:
        """Load Amazon subcategory lookup from CSV file."""
        if not self.lookup_file.exists():
            raise FileNotFoundError(
                f"Subcategory lookup not found: {self.lookup_file}\n"
                f"Expected: {self.lookup_file.absolute()}"
            )
        
        lookup_dict = {}
        with open(self.lookup_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                subcat_name = row['subcategory'].strip()
                lookup_dict[subcat_name] = {
                    'action': row['action'].strip(),
                    'category': row.get('category', '').strip() or None,
                    'subcategory': row.get('subcategory_remap', '').strip() or None
                }
        
        return lookup_dict
    
    def _load_keywords(self) -> List[Dict]:
        """Load non-supplement keywords from CSV file."""
        if not self.keywords_file.exists():
            raise FileNotFoundError(
                f"Keywords file not found: {self.keywords_file}\n"
                f"Expected: {self.keywords_file.absolute()}"
            )
        
        keywords_list = []
        with open(self.keywords_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                keyword = row['keyword'].strip()
                auto_variations = row.get('auto_variations', 'yes').strip().lower() == 'yes'
                exceptions = row.get('exceptions', '').strip()
                exceptions_list = [e.strip() for e in exceptions.split(',') if e.strip()]
                
                keywords_list.append({
                    'keyword': keyword,
                    'category': row.get('category', '').strip(),
                    'auto_variations': auto_variations,
                    'exceptions': exceptions_list,
                    'notes': row.get('notes', '').strip()
                })
        
        return keywords_list
    
    def _generate_keyword_variations(self, keyword: str, auto_variations: bool) -> List[str]:
        """
        Generate all common variations of a keyword to catch messy product titles.
        
        Examples:
        - "essential oil" → ["essential oil", "essentialoil", "essential-oil", "essential_oil", 
                             "essential oils", "essentialoils", "essential-oils", "essential_oils"]
        """
        variations = set()
        
        # Original keyword (lowercase)
        variations.add(keyword.lower())
        
        if auto_variations:
            # No spaces
            no_space = keyword.replace(' ', '')
            variations.add(no_space.lower())
            
            # Hyphenated
            hyphen = keyword.replace(' ', '-')
            variations.add(hyphen.lower())
            
            # Underscore
            underscore = keyword.replace(' ', '_')
            variations.add(underscore.lower())
            
            # Plurals (add 's' to the last word or whole phrase)
            # For single words: "book" → "books"
            # For phrases: "essential oil" → "essential oils"
            words = keyword.split()
            if len(words) == 1:
                plural = keyword + 's'
                variations.add(plural.lower())
                variations.add((plural.replace(' ', '')).lower())
                variations.add((plural.replace(' ', '-')).lower())
                variations.add((plural.replace(' ', '_')).lower())
            else:
                # Pluralize last word
                words[-1] = words[-1] + 's'
                plural_phrase = ' '.join(words)
                variations.add(plural_phrase.lower())
                variations.add(plural_phrase.replace(' ', '').lower())
                variations.add(plural_phrase.replace(' ', '-').lower())
                variations.add(plural_phrase.replace(' ', '_').lower())
        
        return list(variations)
    
    def _generate_patterns(self) -> List[Tuple[str, str, List[str]]]:
        """
        Generate regex patterns from keywords with all variations.
        Returns list of (pattern, original_keyword, exceptions)
        
        For messy product titles, we use substring matching EXCEPT for short words
        where we need word boundaries to avoid false matches like "harvest" → "vest"
        """
        patterns = []
        
        for keyword_data in self.keywords_data:
            keyword = keyword_data['keyword']
            auto_variations = keyword_data['auto_variations']
            exceptions = keyword_data['exceptions']
            
            # Generate all variations
            variations = self._generate_keyword_variations(keyword, auto_variations)
            
            # Create regex pattern for each variation
            for variation in variations:
                # Escape special regex characters
                escaped = re.escape(variation)
                
                # For SHORT single words (<= 4 chars), use word boundaries
                # This avoids false positives like "harvest" matching "vest"
                words = variation.split()
                if len(words) == 1 and len(variation) <= 4:
                    # Single short word - use word boundaries
                    pattern = r'\b' + escaped + r'\b'
                else:
                    # Multi-word or long word - simple substring match
                    pattern = escaped
                
                patterns.append((pattern, keyword, exceptions))
        
        return patterns
    
    def _extract_exceptions(self) -> Dict:
        """Extract exception rules from keywords data."""
        exceptions = {}
        for keyword_data in self.keywords_data:
            if keyword_data['exceptions']:
                keyword = keyword_data['keyword']
                exceptions[keyword] = keyword_data['exceptions']
        return exceptions
    
    def _is_non_supplement_by_title(self, title: str) -> Tuple[bool, str]:
        """Check if title indicates a non-supplement (book, jewelry, etc.)."""
        title_lower = title.lower()
        
        for pattern, original_keyword, exceptions in self.non_supplement_patterns:
            if re.search(pattern, title_lower):
                # Check if this keyword has exceptions
                if original_keyword in self.pattern_exceptions:
                    exception_indicators = self.pattern_exceptions[original_keyword]
                    if any(indicator.lower() in title_lower for indicator in exception_indicators):
                        continue
                
                return True, f"Title keyword filter: '{original_keyword}'"
        
        return False, ""
    
    def filter_dataframe(
        self,
        df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
        if df.empty:
            return df.copy(), pd.DataFrame(), {}
        
        required_cols = ['asin', 'brand', 'title', 'amazon_subcategory']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(
                f"Missing required columns: {missing_cols}\n"
                f"Expected standardized columns. Did you forget to preprocess?"
            )
        
        df_work = df.copy()
        df_work['reasoning'] = None
        df_work['removal_method'] = None  # Track HOW it was removed
        
        removed_indices = []
        unknown_subcategories = {}
        unknown_subcategory_products = {}  # Track products per unknown subcategory
        
        self.total_processed = len(df_work)
        
        for idx, row in df_work.iterrows():
            amazon_subcat = row['amazon_subcategory']
            title = str(row['title'])
            asin = row.get('asin', 'N/A')
            
            # Stage 1: Check Amazon subcategory lookup
            if pd.isna(amazon_subcat) or amazon_subcat == '':
                self.total_not_found += 1
            elif amazon_subcat in self.lookup:
                lookup_entry = self.lookup[amazon_subcat]
                action = lookup_entry.get('action', '')
                
                if action == 'REMOVE':
                    df_work.at[idx, 'reasoning'] = f"Subcategory filter: '{amazon_subcat}'"
                    df_work.at[idx, 'removal_method'] = 'subcategory'
                    removed_indices.append(idx)
                    self.total_removed += 1
                    self.total_removed_by_subcategory += 1
                    continue

                elif action == 'REMAP':
                    self.total_remapped += 1
            else:
                self.total_not_found += 1
                if amazon_subcat not in unknown_subcategories:
                    unknown_subcategories[amazon_subcat] = 0
                    unknown_subcategory_products[amazon_subcat] = []
                unknown_subcategories[amazon_subcat] += 1
                unknown_subcategory_products[amazon_subcat].append({
                    'asin': asin,
                    'brand': row.get('brand', 'N/A'),
                    'title': title  # Full title, not truncated
                })
            
            # Stage 2: Check title for non-supplement keywords (automates manual cleanup)
            is_non_supp, reason = self._is_non_supplement_by_title(title)
            if is_non_supp:
                df_work.at[idx, 'reasoning'] = reason
                df_work.at[idx, 'removal_method'] = 'title'
                removed_indices.append(idx)
                self.total_removed += 1
                self.total_removed_by_title += 1
        
        removed_df = df_work.loc[removed_indices].copy()
        
        # Add standard REMOVE fields to removed products
        if len(removed_df) > 0:
            removed_df['ingredient'] = 'N/A'
            removed_df['category'] = 'REMOVE'
            removed_df['subcategory'] = 'REMOVE'
            removed_df['form'] = 'Other/Unknown'
            removed_df['age'] = 'AGE GROUP - ADULT'
            removed_df['gender'] = 'GENDER - NON SPECIFIC'
            removed_df['health_focus'] = 'UNKNOWN'
            removed_df['organic'] = 'NOT ORGANIC'
            removed_df['high_level_category'] = 'REMOVE'
            removed_df['confidence'] = 'high'
        
        supplements_df = df_work.drop(removed_indices).copy()
        
        stats = {
            'total_input': self.total_processed,
            'removed': self.total_removed,
            'removed_by_subcategory': self.total_removed_by_subcategory,
            'removed_by_title': self.total_removed_by_title,
            'not_in_lookup': self.total_not_found,
            'remapped': self.total_remapped,
            'passed_forward': len(supplements_df),
            'unknown_subcategories': unknown_subcategories,
            'unknown_subcategory_products': unknown_subcategory_products
        }
        
        return supplements_df, removed_df, stats
    
    def save_unknown_subcategories_for_review(
        self,
        unknown_subcategories: Dict[str, int],
        unknown_subcategory_products: Dict[str, List[Dict]],
        output_file: str = 'reference_data/unknown_subcategories_review.csv'
    ):
        """
        Save ALL products with unknown subcategories to CSV for client review.
        Shows every single product so client can make informed decisions.
        This is a REPORT ONLY - client adds decisions to amazon_subcategory_lookup.csv directly.
        """
        if not unknown_subcategories:
            return
        
        import csv
        from pathlib import Path
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['subcategory', 'asin', 'brand', 'title'])
            
            # Sort by count (highest first) for priority review
            for subcat, count in sorted(unknown_subcategories.items(), key=lambda x: x[1], reverse=True):
                # Get ALL products for this subcategory
                products = unknown_subcategory_products.get(subcat, [])
                
                # Write one row per product
                for product in products:
                    asin = product.get('asin', 'N/A')
                    brand = product.get('brand', 'N/A')
                    title = product.get('title', 'N/A')
                    
                    writer.writerow([
                        subcat,
                        asin,
                        brand,
                        title
                    ])
        
        return str(output_path)
    
    def get_stats(self) -> Dict:
        return {
            'total_processed': self.total_processed,
            'total_removed': self.total_removed,
            'total_remapped': self.total_remapped,
            'total_not_found': self.total_not_found,
            'supplements_remaining': self.total_processed - self.total_removed
        }
    
    def get_lookup_info(self) -> Dict:
        remove_count = sum(1 for v in self.lookup.values() if v.get('action') == 'REMOVE')
        remap_count = sum(1 for v in self.lookup.values() if v.get('action') == 'REMAP')
        
        return {
            'lookup_file': str(self.lookup_file),
            'total_entries': len(self.lookup),
            'remove_entries': remove_count,
            'remap_entries': remap_count
        }


def create_subcategory_filter(
    lookup_file: str = 'reference_data/amazon_subcategory_lookup.csv',
    keywords_file: str = 'reference_data/non_supplement_keywords.csv'
) -> SubcategoryFilter:
    return SubcategoryFilter(lookup_file=lookup_file, keywords_file=keywords_file)


def filter_supplements(
    df: pd.DataFrame,
    lookup_file: str = 'reference_data/amazon_subcategory_lookup.csv'
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    filter = create_subcategory_filter(lookup_file)
    return filter.filter_dataframe(df)
