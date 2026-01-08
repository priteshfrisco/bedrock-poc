#!/usr/bin/env python3
"""
High Level Category Assignment
Maps Category to High Level Category (PRIORITY VMS vs NON-PRIORITY VMS vs OTC vs REMOVE)
"""

import json
from pathlib import Path


def load_hlc_rules():
    """Load high-level category mapping rules from postprocessing_rules.json"""
    rules_path = Path(__file__).parent.parent.parent.parent / 'reference_data' / 'postprocessing_rules.json'
    with open(rules_path, 'r', encoding='utf-8') as f:
        rules = json.load(f)
    return rules['high_level_category_mapping']


def assign_high_level_category(category: str) -> str:
    """
    Assign High Level Category based on Category using rules from postprocessing_rules.json.
    
    Logic configurable via JSON (matching R system FinalMerge.R Lines 654-673):
    1. IF Category = "OTC" → "OTC"
    2. ELSE IF Category = "REMOVE" OR Category = None → "REMOVE"
    3. ELSE IF Category = "ACTIVE NUTRITION" → "NON-PRIORITY VMS"
    4. ELSE (all other categories) → "PRIORITY VMS"
    
    Args:
        category: The product category
    
    Returns:
        High Level Category: "PRIORITY VMS", "NON-PRIORITY VMS", "OTC", or "REMOVE"
    """
    
    # Load rules from JSON
    hlc_mapping = load_hlc_rules()
    rules = hlc_mapping['rules']
    default = hlc_mapping.get('default', 'PRIORITY VMS')
    
    # Handle None/empty
    if not category or category == 'N/A' or category == '':
        return "REMOVE"
    
    # Normalize to uppercase for comparison
    category_upper = category.strip().upper()
    
    # Apply rules in priority order
    for rule in sorted(rules, key=lambda x: x['priority']):
        condition = rule['condition']
        
        # Rule: category equals 'OTC'
        if 'equals' in condition and "'OTC'" in condition:
            if category_upper == "OTC":
                return rule['high_level_category']
        
        # Rule: category equals 'REMOVE' OR category is null/empty
        elif 'equals' in condition and "'REMOVE'" in condition:
            if category_upper == "REMOVE":
                return rule['high_level_category']
        
        # Rule: category equals 'ACTIVE NUTRITION'
        elif 'equals' in condition and "'ACTIVE NUTRITION'" in condition:
            if category_upper == "ACTIVE NUTRITION":
                return rule['high_level_category']
        
        # Rule: all other categories (default/fallback)
        elif 'all other' in condition.lower():
            return rule['high_level_category']
    
    # Final fallback
    return default


if __name__ == '__main__':
    # Test cases
    test_cases = [
        ("BASIC VITAMINS & MINERALS", "PRIORITY VMS"),
        ("ACTIVE NUTRITION", "NON-PRIORITY VMS"),
        ("OTC", "OTC"),
        ("REMOVE", "REMOVE"),
        (None, "REMOVE"),
        ("", "REMOVE"),
        ("HERBAL REMEDIES", "PRIORITY VMS"),
        ("COMBINED MULTIVITAMINS", "PRIORITY VMS"),
        ("SPORTS NUTRITION", "PRIORITY VMS"),  # Note: This becomes ACTIVE NUTRITION via business rules
    ]
    
    print("="*80)
    print("HIGH LEVEL CATEGORY TEST")
    print("="*80)
    
    for category, expected in test_cases:
        result = assign_high_level_category(category)
        status = "✅" if result == expected else "❌"
        cat_str = str(category) if category else "None"
        print(f"{status} {cat_str:35s} → {result:20s} (expected: {expected})")

