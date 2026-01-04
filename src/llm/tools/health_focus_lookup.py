#!/usr/bin/env python3
"""
Health Focus Lookup Tool
Uses BM25 + Fuzzy + Exact matching (same as ingredient lookup)
Maps ingredient name to health focus category
"""

import csv
import os
from rapidfuzz import fuzz, process
from rank_bm25 import BM25Okapi


class HealthFocusLookup:
    """Singleton class for Health Focus lookup with BM25 + Fuzzy matching"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._load_data()
            self._initialized = True
    
    def _load_data(self):
        """Load health focus lookup data"""
        csv_path = 'reference_data/ingredient_health_focus_lookup.csv'
        
        self.data = []
        self.ingredient_to_hf = {}
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ingredient = row['ingredient'].strip()
                health_focus = row['health_focus'].strip()
                
                if ingredient and health_focus:
                    ingredient_lower = ingredient.lower()
                    self.data.append({
                        'ingredient': ingredient,
                        'ingredient_lower': ingredient_lower,
                        'health_focus': health_focus
                    })
                    self.ingredient_to_hf[ingredient_lower] = health_focus
        
        # Build BM25 index
        tokenized_ingredients = [entry['ingredient_lower'].split() for entry in self.data]
        self.bm25 = BM25Okapi(tokenized_ingredients)
        
        print(f"✅ Loaded {len(self.data)} ingredients with health focus mappings")
    
    def lookup(self, ingredient_name: str) -> dict:
        """
        Look up health focus for an ingredient
        
        Args:
            ingredient_name: Name of ingredient to look up
        
        Returns:
            dict with keys:
            - found: bool
            - ingredient: normalized ingredient name
            - health_focus: health focus category
            - match_type: 'exact', 'fuzzy', or 'bm25'
            - confidence: 'exact', 'high', 'medium', 'low'
            - score: numeric score (100 for exact, 0-100 for fuzzy/BM25)
        """
        
        if not ingredient_name or not isinstance(ingredient_name, str):
            return {
                'found': False,
                'ingredient': None,
                'health_focus': None,
                'match_type': None,
                'confidence': None,
                'score': 0
            }
        
        query = ingredient_name.strip().lower()
        
        # STEP 1: Exact match
        if query in self.ingredient_to_hf:
            return {
                'found': True,
                'ingredient': next(e['ingredient'] for e in self.data if e['ingredient_lower'] == query),
                'health_focus': self.ingredient_to_hf[query],
                'match_type': 'exact',
                'confidence': 'exact',
                'score': 100
            }
        
        # STEP 2: Fuzzy match
        ingredient_names = [e['ingredient_lower'] for e in self.data]
        fuzzy_results = process.extract(
            query,
            ingredient_names,
            scorer=fuzz.ratio,
            limit=5
        )
        
        best_fuzzy_match, fuzzy_score, _ = fuzzy_results[0] if fuzzy_results else (None, 0, None)
        
        if fuzzy_score >= 90:
            matched_entry = next(e for e in self.data if e['ingredient_lower'] == best_fuzzy_match)
            return {
                'found': True,
                'ingredient': matched_entry['ingredient'],
                'health_focus': matched_entry['health_focus'],
                'match_type': 'fuzzy',
                'confidence': 'high' if fuzzy_score >= 95 else 'medium',
                'score': fuzzy_score
            }
        
        # STEP 3: BM25 (for multi-word queries)
        tokenized_query = query.split()
        if len(tokenized_query) > 1:
            bm25_scores = self.bm25.get_scores(tokenized_query)
            best_idx = bm25_scores.argmax()
            best_score = bm25_scores[best_idx]
            
            if best_score > 5:  # BM25 threshold
                matched_entry = self.data[best_idx]
                
                # Also check fuzzy score for this match
                fuzzy_check = fuzz.ratio(query, matched_entry['ingredient_lower'])
                
                if fuzzy_check >= 75 or best_score > 10:
                    confidence = 'high' if best_score > 10 else 'medium'
                    return {
                        'found': True,
                        'ingredient': matched_entry['ingredient'],
                        'health_focus': matched_entry['health_focus'],
                        'match_type': 'bm25',
                        'confidence': confidence,
                        'score': round(best_score, 2)
                    }
        
        # STEP 4: Lower threshold fuzzy match (60-89)
        if 60 <= fuzzy_score < 90:
            matched_entry = next(e for e in self.data if e['ingredient_lower'] == best_fuzzy_match)
            return {
                'found': True,
                'ingredient': matched_entry['ingredient'],
                'health_focus': matched_entry['health_focus'],
                'match_type': 'fuzzy',
                'confidence': 'low',
                'score': fuzzy_score
            }
        
        # No match found
        return {
            'found': False,
            'ingredient': ingredient_name,
            'health_focus': None,
            'match_type': None,
            'confidence': None,
            'score': 0
        }


# Singleton instance
_health_focus_lookup_instance = None


def lookup_health_focus(ingredient_name: str) -> dict:
    """
    Look up health focus for an ingredient (called directly from Python post-processing)
    
    NOTE: This is NOT an LLM tool - it's called directly from Python after business rules
    determine the primary ingredient.
    
    Args:
        ingredient_name: Name of ingredient to look up
    
    Returns:
        dict with health focus information
    """
    global _health_focus_lookup_instance
    
    if _health_focus_lookup_instance is None:
        _health_focus_lookup_instance = HealthFocusLookup()
    
    return _health_focus_lookup_instance.lookup(ingredient_name)


if __name__ == '__main__':
    # Test the lookup
    print("="*80)
    print("HEALTH FOCUS LOOKUP TEST")
    print("="*80)
    
    test_ingredients = [
        "calcium",
        "cranberry",
        "melatonin",
        "turmeric",
        "collagen",
        "probiotics",
        "vitamin d",
        "fish oil"
    ]
    
    for ing in test_ingredients:
        result = lookup_health_focus(ing)
        print(f"\n{ing}:")
        print(f"  Found: {result['found']}")
        if result['found']:
            print(f"  Health Focus: {result['health_focus']}")
            print(f"  Match Type: {result['match_type']}")
            print(f"  Confidence: {result['confidence']}")
            print(f"  Score: {result['score']}")

