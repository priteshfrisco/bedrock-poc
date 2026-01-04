#!/usr/bin/env python3
"""
High Level Category Assignment
Maps Category to High Level Category (PRIORITY VMS vs NON-PRIORITY VMS vs OTC vs REMOVE)
"""


def assign_high_level_category(category: str) -> str:
    """
    Assign High Level Category based on Category
    
    Logic from R system (FinalMerge.R Lines 654-673):
    1. IF Category = "OTC" → "OTC"
    2. ELSE IF Category = "REMOVE" OR Category = None → "REMOVE"
    3. ELSE IF Category = "ACTIVE NUTRITION" → "NON-PRIORITY VMS"
    4. ELSE (all other categories) → "PRIORITY VMS"
    
    Args:
        category: The product category
    
    Returns:
        High Level Category: "PRIORITY VMS", "NON-PRIORITY VMS", "OTC", or "REMOVE"
    """
    
    # Handle None/empty
    if not category or category == 'N/A':
        return "REMOVE"
    
    # Normalize to uppercase for comparison
    category_upper = category.strip().upper()
    
    # Rule 1: OTC
    if category_upper == "OTC":
        return "OTC"
    
    # Rule 2: REMOVE or missing
    if category_upper == "REMOVE":
        return "REMOVE"
    
    # Rule 3: NON-PRIORITY VMS (only ACTIVE NUTRITION)
    if category_upper == "ACTIVE NUTRITION":
        return "NON-PRIORITY VMS"
    
    # Rule 4: Everything else is PRIORITY VMS
    return "PRIORITY VMS"


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

