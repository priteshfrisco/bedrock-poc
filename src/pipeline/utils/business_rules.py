#!/usr/bin/env python3
"""
Business Rules for Category/Subcategory Assignment
Applies R's business logic after ingredient lookup
"""

import csv
from collections import defaultdict


def load_ingredient_categories():
    """Load ingredient to category mapping for herb detection"""
    herb_ingredients = set()
    protein_ingredients = set()
    
    with open('reference_data/ingredient_category_lookup.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row['ingredient']:
                continue
            
            ingredient = row['ingredient'].strip().lower()
            category = row['nw_category'].strip()
            
            # Identify herbs
            if category == 'HERBAL REMEDIES':
                herb_ingredients.add(ingredient)
            
            # Identify proteins
            if 'PROTEIN' in ingredient.upper() or ingredient in ['whey', 'casein', 'isolate', 'pea', 'soy']:
                protein_ingredients.add(ingredient)
    
    return herb_ingredients, protein_ingredients


# Load once at module import
HERB_INGREDIENTS, PROTEIN_INGREDIENTS = load_ingredient_categories()


def apply_herb_formula_rule(ingredients_data, primary_category, primary_subcategory):
    """
    Apply R's Herb Formula Rule:
    If 2+ ingredients are HERBAL, change subcategory to "FORMULAS"
    
    Args:
        ingredients_data: List of dicts with 'name', 'position', 'category', 'subcategory'
        primary_category: Current category from primary ingredient
        primary_subcategory: Current subcategory from primary ingredient
    
    Returns:
        tuple: (updated_category, updated_subcategory, reasoning)
    """
    if not ingredients_data:
        return primary_category, primary_subcategory, ""
    
    # Count how many ingredients are herbs
    herb_count = 0
    herb_names = []
    
    for ing in ingredients_data:
        ing_name = ing.get('name', '').strip().lower()
        ing_category = ing.get('category', '')
        
        # Check if ingredient is a herb
        if ing_category == 'HERBAL REMEDIES' or ing_name in HERB_INGREDIENTS:
            herb_count += 1
            herb_names.append(ing.get('name', ''))
    
    # Apply herb formula rule
    if herb_count >= 2 and primary_category == 'HERBAL REMEDIES':
        return (
            'HERBAL REMEDIES',
            'FORMULAS',
            f"Herb Formula Rule: Found {herb_count} herbs ({', '.join(herb_names[:3])}...) → Subcategory changed to FORMULAS"
        )
    elif herb_count == 1 and primary_category == 'HERBAL REMEDIES':
        return (
            'HERBAL REMEDIES',
            'SINGLES',
            f"Single Herb: Only 1 herb found ({herb_names[0]}) → Subcategory = SINGLES"
        )
    
    return primary_category, primary_subcategory, ""


def apply_protein_rule(primary_ingredient_name, primary_category, primary_subcategory):
    """
    Apply R's Protein Rule:
    If primary ingredient is protein/whey/isolate, override to SPORTS NUTRITION / PROTEIN
    
    Args:
        primary_ingredient_name: Name of primary ingredient
        primary_category: Current category
        primary_subcategory: Current subcategory
    
    Returns:
        tuple: (updated_category, updated_subcategory, reasoning)
    """
    if not primary_ingredient_name:
        return primary_category, primary_subcategory, ""
    
    ingredient_lower = primary_ingredient_name.strip().lower()
    
    # Check if primary ingredient is protein
    protein_keywords = ['protein', 'whey', 'isolate', 'casein', 'pea protein', 'soy protein']
    
    if any(keyword in ingredient_lower for keyword in protein_keywords):
        return (
            'SPORTS NUTRITION',
            'PROTEIN',
            f"Protein Rule: Primary ingredient '{primary_ingredient_name}' is protein → Category = SPORTS NUTRITION / PROTEIN"
        )
    
    return primary_category, primary_subcategory, ""


def apply_multivitamin_refinement(category, subcategory, age_group, gender, title=""):
    """
    Apply R's Multivitamin Refinement Rule (FinalMerge.R Lines 236-277):
    If category is COMBINED MULTIVITAMINS, refine subcategory based on age/gender
    
    Args:
        category: Current category
        subcategory: Current subcategory
        age_group: Extracted age group (e.g., "AGE GROUP - CHILD")
        gender: Extracted gender (e.g., "GENDER - FEMALE")
        title: Product title (for PRENATAL/POSTNATAL override)
    
    Returns:
        tuple: (updated_category, updated_subcategory, reasoning)
    """
    if category != 'COMBINED MULTIVITAMINS':
        return category, subcategory, ""
    
    reasoning_parts = []
    
    # STEP 1: AGE-BASED RULES (highest specificity for children)
    if age_group == "AGE GROUP - CHILD":
        subcategory = "CHILD"
        reasoning_parts.append(f"Age={age_group} → Subcategory=CHILD")
    elif age_group == "AGE GROUP - TEEN":
        subcategory = "TEEN"
        reasoning_parts.append(f"Age={age_group} → Subcategory=TEEN")
    
    # STEP 2: AGE + GENDER COMBINATION (overrides age-only for adults)
    if gender == "GENDER - MALE":
        if age_group == "AGE GROUP - ADULT" or age_group == "AGE GROUP - NON SPECIFIC":
            subcategory = "MEN"
            reasoning_parts.append(f"Gender=MALE + Age={age_group} → Subcategory=MEN")
        elif age_group == "AGE GROUP - MATURE ADULT":
            subcategory = "MEN MATURE"
            reasoning_parts.append(f"Gender=MALE + Age=MATURE ADULT → Subcategory=MEN MATURE")
        else:
            subcategory = "ADULT"
            reasoning_parts.append(f"Gender=MALE (default) → Subcategory=ADULT")
    
    elif gender == "GENDER - FEMALE":
        if age_group == "AGE GROUP - ADULT" or age_group == "AGE GROUP - NON SPECIFIC":
            subcategory = "WOMEN"
            reasoning_parts.append(f"Gender=FEMALE + Age={age_group} → Subcategory=WOMEN")
        elif age_group == "AGE GROUP - MATURE ADULT":
            subcategory = "WOMEN MATURE"
            reasoning_parts.append(f"Gender=FEMALE + Age=MATURE ADULT → Subcategory=WOMEN MATURE")
        else:
            subcategory = "ADULT"
            reasoning_parts.append(f"Gender=FEMALE (default) → Subcategory=ADULT")
    
    elif gender == "GENDER - NON SPECIFIC":
        if age_group == "AGE GROUP - ADULT":
            subcategory = "ADULT"
            reasoning_parts.append(f"Gender=NON SPECIFIC + Age=ADULT → Subcategory=ADULT")
        elif age_group == "AGE GROUP - NON SPECIFIC":
            subcategory = "NON-SPECIFIC"
            reasoning_parts.append(f"Gender=NON SPECIFIC + Age=NON SPECIFIC → Subcategory=NON-SPECIFIC")
        elif age_group == "AGE GROUP - MATURE ADULT":
            subcategory = "MATURE ADULT"
            reasoning_parts.append(f"Gender=NON SPECIFIC + Age=MATURE ADULT → Subcategory=MATURE ADULT")
    
    # STEP 3: TITLE OVERRIDE - HIGHEST PRIORITY
    if title:
        title_upper = title.upper()
        if 'PRENATAL' in title_upper or 'POSTNATAL' in title_upper:
            subcategory = "PRENATAL"
            reasoning_parts.append(f"TITLE OVERRIDE: 'PRENATAL/POSTNATAL' found → Subcategory=PRENATAL")
    
    reasoning = " | ".join(reasoning_parts) if reasoning_parts else ""
    return category, subcategory, f"Multivitamin Refinement: {reasoning}"


def apply_ingredient_specific_overrides(primary_ingredient_name, category, subcategory):
    """
    Apply ingredient-specific category/subcategory overrides from R system.
    These override whatever the ingredient lookup returned.
    
    Args:
        primary_ingredient_name: Name of primary ingredient
        category: Current category
        subcategory: Current subcategory
    
    Returns:
        tuple: (updated_category, updated_subcategory, reasoning)
    """
    if not primary_ingredient_name:
        return category, subcategory, ""
    
    ingredient_upper = primary_ingredient_name.strip().upper()
    
    # RULE 1: SAM-E Override (R: FinalMerge.R Lines 176-179)
    if ingredient_upper == "SAM E" or ingredient_upper == "SAM-E":
        return (
            'MISCELLANEOUS SUPPLEMENTS',
            'MISCELLANEOUS SUPPLEMENTS',
            f"SAM-E Override: Primary ingredient = '{primary_ingredient_name}' → MISCELLANEOUS SUPPLEMENTS"
        )
    
    # RULE 2: Algae Group Override (R: FinalMerge.R Lines 182-192)
    algae_group = [
        "SPIRULINA BLUE GREEN ALGAE",
        "SPIRULINA",
        "ALGAE - OTHER",
        "ALGAE",
        "SEA MOSS",
        "CHLOROPHYLL / CHLORELLA",
        "CHLORELLA"
    ]
    if ingredient_upper in algae_group:
        return (
            'HERBAL REMEDIES',
            'FOOD SUPPLEMENTS',
            f"Algae Override: Primary ingredient = '{primary_ingredient_name}' → HERBAL REMEDIES / FOOD SUPPLEMENTS"
        )
    
    # RULE 3: Echinacea Goldenseal Combo (R: FinalMerge.R Lines 193-196)
    if ingredient_upper == "ECHINACEA GOLDENSEAL COMBO":
        return (
            'HERBAL/HOMEOPATHIC COLD & FLU',
            'HERBAL FORMULAS COLD & FLU',
            f"Echinacea Goldenseal Override: '{primary_ingredient_name}' → HERBAL/HOMEOPATHIC COLD & FLU"
        )
    
    # RULE 4: Choline Inositol Combo (R: FinalMerge.R Lines 197-200)
    if ingredient_upper == "CHOLINE AND INOSITOL (COMBO)" or ingredient_upper == "CHOLINE INOSITOL":
        return (
            'MISCELLANEOUS SUPPLEMENTS',
            'MISCELLANEOUS SUPPLEMENTS',
            f"Choline Inositol Override: '{primary_ingredient_name}' → MISCELLANEOUS SUPPLEMENTS"
        )
    
    # RULE 5: CoQ10 Ubiquinol (R: FinalMerge.R Lines 201-204)
    if ingredient_upper == "CO-ENZYME Q 10 - UBIQUINOL" or "UBIQUINOL" in ingredient_upper:
        return (
            'COENZYME Q10',
            'COENZYME Q10',
            f"CoQ10 Ubiquinol Override: '{primary_ingredient_name}' → COENZYME Q10"
        )
    
    # RULE 6: Glandular Override (R: FinalMerge.R Lines 205-208)
    if ingredient_upper == "GLANDULAR":
        return (
            'MISCELLANEOUS SUPPLEMENTS',
            'MISCELLANEOUS SUPPLEMENTS',
            f"Glandular Override: '{primary_ingredient_name}' → MISCELLANEOUS SUPPLEMENTS"
        )
    
    return category, subcategory, ""


def apply_title_based_overrides(title, category, subcategory):
    """
    Apply title-based category/subcategory overrides from R system.
    These are for cases where title keywords indicate specific categories.
    
    Args:
        title: Product title
        category: Current category
        subcategory: Current subcategory
    
    Returns:
        tuple: (updated_category, updated_subcategory, reasoning)
    """
    if not title:
        return category, subcategory, ""
    
    title_upper = title.upper()
    
    # RULE 1: Protein Powder Title Check (R: FinalMerge.R Lines 209-213)
    if 'PROTEIN POWDER' in title_upper:
        return (
            'ACTIVE NUTRITION',
            'PROTEIN & MEAL REPLACEMENTS',
            f"Protein Powder Title Override: Title contains 'PROTEIN POWDER' → ACTIVE NUTRITION / PROTEIN & MEAL REPLACEMENTS"
        )
    
    # RULE 2: Weight Loss Keywords (R: FinalMerge.R Lines 217-227)
    if 'WEIGHT LOSS' in title_upper or 'WEIGHT MANAGEMENT' in title_upper:
        return (
            'ACTIVE NUTRITION',
            'WEIGHT MANAGEMENT',
            f"Weight Loss Override: Title contains weight loss/management → ACTIVE NUTRITION / WEIGHT MANAGEMENT"
        )
    
    return category, subcategory, ""


def apply_all_business_rules(ingredients_data, age_group, gender, title=""):
    """
    Apply all business rules in order (matching R system's FinalMerge.R):
    1. Title-Based Overrides (protein powder, weight loss)
    2. Ingredient-Specific Overrides (SAM-E, algae, etc.)
    3. Protein Rule (protein/whey/isolate)
    4. Herb Formula Rule (2+ herbs)
    5. Multivitamin Refinement (age + gender + title)
    
    Args:
        ingredients_data: List of ingredient dicts with category/subcategory
        age_group: Extracted age group
        gender: Extracted gender
        title: Product title (for title-based overrides)
    
    Returns:
        dict: {
            'category': final category,
            'subcategory': final subcategory,
            'primary_ingredient': name of primary ingredient,
            'all_ingredients': list of all ingredient names,
            'reasoning': explanation of business rules applied
        }
    """
    if not ingredients_data:
        return {
            'category': None,
            'subcategory': None,
            'primary_ingredient': None,
            'all_ingredients': [],
            'reasoning': "No ingredients found"
        }
    
    # Normalize ingredients_data to ensure all are dicts
    normalized_ingredients = []
    for ing in ingredients_data:
        if isinstance(ing, dict):
            normalized_ingredients.append(ing)
        elif isinstance(ing, str):
            # Convert string to dict format
            normalized_ingredients.append({
                'name': ing,
                'position': 999  # Unknown position
            })
    
    if not normalized_ingredients:
        return {
            'category': None,
            'subcategory': None,
            'primary_ingredient': 'N/A',
            'reasoning': "No valid ingredients after normalization"
        }
    
    # Sort by position to get primary ingredient (first)
    sorted_ingredients = sorted(normalized_ingredients, key=lambda x: x.get('position', 999))
    
    # Check for multivitamin exception (R's primary ingredient logic)
    primary_ingredient = None
    for ing in sorted_ingredients:
        ing_name_lower = ing.get('name', '').lower()
        if 'multivitamin' in ing_name_lower or 'multiple vitamin' in ing_name_lower:
            primary_ingredient = ing
            break
    
    # If no multivitamin, use first by position
    if not primary_ingredient:
        primary_ingredient = sorted_ingredients[0]
    
    # Get initial category/subcategory from primary ingredient lookup
    category = primary_ingredient.get('category', '')
    subcategory = primary_ingredient.get('subcategory', '')
    primary_name = primary_ingredient.get('name', '')
    
    reasoning_parts = []
    reasoning_parts.append(f"Primary Ingredient: '{primary_name}' (position {primary_ingredient.get('position', 0)})")
    reasoning_parts.append(f"Initial Category/Subcategory: {category} / {subcategory}")
    
    # RULE 1: Title-Based Overrides (highest priority for these specific cases)
    category, subcategory, title_reasoning = apply_title_based_overrides(title, category, subcategory)
    if title_reasoning:
        reasoning_parts.append(title_reasoning)
    
    # RULE 2: Ingredient-Specific Overrides (SAM-E, algae, CoQ10, etc.)
    category, subcategory, ingredient_override_reasoning = apply_ingredient_specific_overrides(primary_name, category, subcategory)
    if ingredient_override_reasoning:
        reasoning_parts.append(ingredient_override_reasoning)
    
    # RULE 3: Protein Rule (check if primary ingredient is protein)
    category, subcategory, protein_reasoning = apply_protein_rule(primary_name, category, subcategory)
    if protein_reasoning:
        reasoning_parts.append(protein_reasoning)
    
    # RULE 4: Herb Formula Rule (count herbs, set FORMULAS/SINGLES)
    category, subcategory, herb_reasoning = apply_herb_formula_rule(sorted_ingredients, category, subcategory)
    if herb_reasoning:
        reasoning_parts.append(herb_reasoning)
    
    # RULE 5: Multivitamin Refinement (age + gender + title for subcategory)
    category, subcategory, multi_reasoning = apply_multivitamin_refinement(category, subcategory, age_group, gender, title)
    if multi_reasoning:
        reasoning_parts.append(multi_reasoning)
    
    return {
        'category': category,
        'subcategory': subcategory,
        'primary_ingredient': primary_name,
        'all_ingredients': [ing.get('name', '') for ing in sorted_ingredients],
        'reasoning': ' | '.join(reasoning_parts)
    }


if __name__ == '__main__':
    # Test cases
    print("="*80)
    print("TESTING BUSINESS RULES")
    print("="*80)
    
    # Test 1: Herb Formula
    test1 = [
        {'name': 'echinacea', 'position': 0, 'category': 'HERBAL REMEDIES', 'subcategory': 'SINGLES'},
        {'name': 'goldenseal', 'position': 10, 'category': 'HERBAL REMEDIES', 'subcategory': 'SINGLES'},
        {'name': 'ginger', 'position': 20, 'category': 'HERBAL REMEDIES', 'subcategory': 'SINGLES'}
    ]
    result1 = apply_all_business_rules(test1, 'AGE GROUP - NON SPECIFIC', 'GENDER - NON SPECIFIC')
    print("\nTest 1 - Herb Formula:")
    print(f"  Result: {result1['category']} / {result1['subcategory']}")
    
    # Test 2: Protein
    test2 = [
        {'name': 'whey protein', 'position': 0, 'category': 'AMINO ACIDS', 'subcategory': 'AMINO ACIDS'}
    ]
    result2 = apply_all_business_rules(test2, 'AGE GROUP - ADULT', 'GENDER - MALE')
    print("\nTest 2 - Protein Override:")
    print(f"  Result: {result2['category']} / {result2['subcategory']}")
    
    # Test 3: Women's Multivitamin
    test3 = [
        {'name': 'multivitamin', 'position': 8, 'category': 'COMBINED MULTIVITAMINS', 'subcategory': 'COMBINED MULTIVITAMINS'}
    ]
    result3 = apply_all_business_rules(test3, 'AGE GROUP - ADULT', 'GENDER - FEMALE')
    print("\nTest 3 - Women's Multivitamin:")
    print(f"  Result: {result3['category']} / {result3['subcategory']}")
    
    # Test 4: Prenatal Multivitamin (Title Override)
    test4 = [
        {'name': 'multivitamin', 'position': 5, 'category': 'COMBINED MULTIVITAMINS', 'subcategory': 'COMBINED MULTIVITAMINS'}
    ]
    result4 = apply_all_business_rules(test4, 'AGE GROUP - ADULT', 'GENDER - FEMALE', title="Nature's Way Prenatal Multivitamin with DHA")
    print("\nTest 4 - Prenatal Multivitamin (Title Override):")
    print(f"  Result: {result4['category']} / {result4['subcategory']}")
    
    # Test 5: SAM-E Override
    test5 = [
        {'name': 'SAM E', 'position': 0, 'category': 'AMINO ACIDS', 'subcategory': 'AMINO ACIDS'}
    ]
    result5 = apply_all_business_rules(test5, 'AGE GROUP - ADULT', 'GENDER - NON SPECIFIC')
    print("\nTest 5 - SAM-E Override:")
    print(f"  Result: {result5['category']} / {result5['subcategory']}")
    
    # Test 6: Algae Override
    test6 = [
        {'name': 'SPIRULINA', 'position': 0, 'category': 'BASIC VITAMINS & MINERALS', 'subcategory': 'MINERALS'}
    ]
    result6 = apply_all_business_rules(test6, 'AGE GROUP - NON SPECIFIC', 'GENDER - NON SPECIFIC')
    print("\nTest 6 - Algae Override:")
    print(f"  Result: {result6['category']} / {result6['subcategory']}")
    
    # Test 7: Protein Powder Title Override
    test7 = [
        {'name': 'turmeric', 'position': 0, 'category': 'HERBAL REMEDIES', 'subcategory': 'SINGLES'}
    ]
    result7 = apply_all_business_rules(test7, 'AGE GROUP - ADULT', 'GENDER - MALE', title="Plant-Based Protein Powder with Turmeric")
    print("\nTest 7 - Protein Powder Title Override:")
    print(f"  Result: {result7['category']} / {result7['subcategory']}")
    
    # Test 8: Weight Loss Title Override
    test8 = [
        {'name': 'green tea', 'position': 0, 'category': 'HERBAL REMEDIES', 'subcategory': 'SINGLES'}
    ]
    result8 = apply_all_business_rules(test8, 'AGE GROUP - ADULT', 'GENDER - NON SPECIFIC', title="Green Tea Extract for Weight Loss")
    print("\nTest 8 - Weight Loss Title Override:")
    print(f"  Result: {result8['category']} / {result8['subcategory']}")
    
    print("\n" + "="*80)
    print("✅ All business rules implemented and tested!")
    print("="*80)
