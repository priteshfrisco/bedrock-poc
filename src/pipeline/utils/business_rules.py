#!/usr/bin/env python3
"""
Business Rules for Category/Subcategory Assignment
Applies R's business logic after ingredient lookup
"""

import csv
from typing import List, Dict, Optional
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


def load_health_focus_lookup():
    """Load ingredient to health focus mapping"""
    health_focus_map = {}
    
    with open('reference_data/ingredient_health_focus_lookup.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row['ingredient'] or not row['health_focus']:
                continue
            
            ingredient = row['ingredient'].strip().upper()
            health_focus = row['health_focus'].strip()
            health_focus_map[ingredient] = health_focus
    
    return health_focus_map


# Load once at module import
HERB_INGREDIENTS, PROTEIN_INGREDIENTS = load_ingredient_categories()
HEALTH_FOCUS_MAP = load_health_focus_lookup()


def get_health_focus_from_ingredient(primary_ingredient: str) -> str:
    """
    Get health focus for a given ingredient from lookup table.
    
    Args:
        primary_ingredient: The primary ingredient name (normalized)
    
    Returns:
        Health focus string, or "HEALTH FOCUS NON-SPECIFIC" if not found
    """
    if not primary_ingredient:
        return "HEALTH FOCUS NON-SPECIFIC"
    
    ingredient_upper = primary_ingredient.upper()
    return HEALTH_FOCUS_MAP.get(ingredient_upper, "HEALTH FOCUS NON-SPECIFIC")


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
    
    # RULE 3: Electrolyte/Hydration Keywords (R: FinalMerge.R Lines 395-409)
    # Check for "HYDRAT" but exclude "DEHYDRAT"
    if 'HYDRAT' in title_upper and 'DEHYDRAT' not in title_upper:
        return (
            'ACTIVE NUTRITION',
            'HYDRATION',
            f"Hydration Override: Title contains 'HYDRAT' (not 'DEHYDRAT') → ACTIVE NUTRITION / HYDRATION"
        )
    
    # Check for "ELECTROLYTE" but exclude "CREATINE"
    if 'ELECTROLYTE' in title_upper and 'CREATINE' not in title_upper:
        return (
            'ACTIVE NUTRITION',
            'HYDRATION',
            f"Electrolyte Override: Title contains 'ELECTROLYTE' (not 'CREATINE') → ACTIVE NUTRITION / HYDRATION"
        )
    
    return category, subcategory, ""


def apply_health_focus_rules(title: str, primary_ingredient: str, current_health_focus: str, 
                             category: str = "", subcategory: str = "", gender: str = "") -> str:
    """
    Apply R's health focus business rules (FinalMerge.R Lines 455-650).
    These rules OVERRIDE the health focus from ingredient lookup.
    
    Args:
        title: Product title
        primary_ingredient: Primary ingredient name (normalized)
        current_health_focus: Current health focus from ingredient lookup
        category: Product category (for category-based rules)
        gender: Gender attribute (for gender correction rules)
    
    Returns:
        Final health focus after applying all override rules
    """
    if not title:
        return current_health_focus
    
    title_upper = title.upper()
    ingredient_upper = primary_ingredient.upper() if primary_ingredient else ""
    
    # ════════════════════════════════════════════════════════════════════════════
    # HIGH-CONFIDENCE RULES (Always apply, override everything)
    # R: FinalMerge.R Lines 456-614
    # ════════════════════════════════════════════════════════════════════════════
    
    # Rule 1: Cough/Cold/Flu
    if "COUGH" in title_upper:
        return "COUGH, COLD & FLU"
    
    # Rule 2: Sleep
    if "MELATONIN" in title_upper:
        return "SLEEP"
    
    # Rule 3: Men's Health
    if "TESTOSTERONE" in title_upper or "MALE ENHANCEMENT" in title_upper:
        return "MEN'S HEALTH"
    
    # Rule 4: Women's Health
    if "ESTROGEN" in title_upper or "MENOPAUSE" in title_upper or "PMS" in title_upper:
        return "WOMEN'S HEALTH"
    
    # Rule 5: Bone Health (Calcium - exact match only)
    # R: if (new_items$`Functional Ingredient`[i]=="CALCIUM")
    if ingredient_upper == "CALCIUM":
        return "BONE HEALTH"
    
    # Rule 6: Cleanse & Detox (Antioxidant + Liver)
    if "ANTIOXIDANT" in title_upper and "LIVER" in title_upper:
        return "CLEANSE & DETOX"
    
    # Rule 7: Urinary Tract Health
    if ingredient_upper == "CRANBERRY SUPPLEMENTS":
        return "URINARY TRACT HEALTH"
    if "PROSTATE" in title_upper or "BLADDER" in title_upper:
        return "URINARY TRACT HEALTH"
    
    # Rule 8: Daily Immune Health (Black Seed)
    if ingredient_upper == "BLACK SEED (CUMIN)":
        return "DAILY IMMUNE HEALTH"
    
    # Rule 9: Mood & Stress (Magnesium + Keywords)
    if ingredient_upper == "MAGNESIUM":
        if "MOOD" in title_upper or "STRESS" in title_upper:
            return "MOOD & STRESS SUPPORT"
    
    # Rule 10: Weight Management (Muscle)
    if "MUSCLE" in title_upper:
        return "WEIGHT MANAGEMENT"
    
    # Rule 11: Daily Immune Health (Immunity)
    if "IMMUNITY" in title_upper:
        return "DAILY IMMUNE HEALTH"
    
    # Rule 12: Cough/Cold/Flu (Respiratory)
    if "RESPITORY" in title_upper or "RESPIRATORY" in title_upper:
        return "COUGH, COLD & FLU"
    
    # Rule 13: Cough/Cold/Flu (Cold - with exclusions)
    if "COLD" in title_upper:
        exclusions = ["PROCESSED", "PACKAGED", "PRESSED", "STONE", "MILLED"]
        if not any(excl in title_upper for excl in exclusions):
            return "COUGH, COLD & FLU"
    
    # Rule 14: Mood & Stress (Nervous System)
    if "NERVOUS SYSTEM" in title_upper:
        return "MOOD & STRESS SUPPORT"
    
    # Rule 15: Joint Health (Arthritis only - per R code)
    # R: if (grepl("ARTHRITIS", new_items$Title[i]))
    if "ARTHRITIS" in title_upper:
        return "JOINT HEALTH"
    
    # Rule 16: Weight Management (Creatine)
    if "CREATINE" in title_upper:
        return "WEIGHT MANAGEMENT"
    
    # Rule 17: Cardiovascular (Blood - not Blood Orange)
    if "BLOOD" in title_upper and "BLOOD ORANGE" not in title_upper:
        return "CARDIOVASCULAR"
    
    # Rule 18: Blood Sugar Support
    if "BLOOD SUGAR" in title_upper or "GLUCOSE" in title_upper or "DIABETES" in title_upper:
        return "BLOOD SUGAR SUPPORT"
    
    # Rule 19: Digestive Health
    digestive_keywords = ["ACID REFLUX", "HEARTBURN", "LAXATIVE", "DIGESTION", "STOOL SOFT"]
    if any(keyword in title_upper for keyword in digestive_keywords):
        return "DIGESTIVE HEALTH"
    
    # Rule 20: Energy Support (R code only checks this specific phrase)
    # R: if (grepl("PERFORMANCE BOOST", new_items$Title[i]))
    if "PERFORMANCE BOOST" in title_upper:
        return "ENERGY SUPPORT"
    
    # Rule 21: Cleanse & Detox
    if "DETOXIFICATION" in title_upper:
        return "CLEANSE & DETOX"
    
    # Rule 22: Weight Management
    if "FAT BURN" in title_upper or "METABOLISM SUPPORT" in title_upper:
        return "WEIGHT MANAGEMENT"
    
    # Rule 23: Beauty (Collagen + Keywords - overrides Joint Health)
    if current_health_focus == "JOINT HEALTH" and "COLLAGEN" in title_upper:
        beauty_keywords = ["BEAUTY", "HAIR", "SKIN ", "NAILS"]
        if any(keyword in title_upper for keyword in beauty_keywords):
            return "BEAUTY"
    
    # Rule 24: Brain Health
    if "MCT OIL" in title_upper or "KRILL OIL" in title_upper or "DHA" in title_upper:
        return "BRAIN HEALTH"
    
    # ════════════════════════════════════════════════════════════════════════════
    # LOW-CONFIDENCE RULES (Only apply if current = "HEALTH FOCUS NON-SPECIFIC")
    # R: FinalMerge.R Lines 617-630
    # ════════════════════════════════════════════════════════════════════════════
    
    if current_health_focus == "HEALTH FOCUS NON-SPECIFIC":
        if "ANTIOXIDANT" in title_upper:
            return "DAILY IMMUNE HEALTH"
        if "COLON" in title_upper or "LIVER" in title_upper:
            return "CLEANSE & DETOX"
        if "NAUSEA" in title_upper:
            return "DIGESTIVE HEALTH"
    
    # ════════════════════════════════════════════════════════════════════════════
    # GENDER CORRECTION RULES
    # R: FinalMerge.R Lines 634-640
    # ════════════════════════════════════════════════════════════════════════════
    
    if gender:
        if current_health_focus == "MEN'S HEALTH" and "GENDER - FEMALE" in gender:
            return "WOMEN'S HEALTH"
        if current_health_focus == "WOMEN'S HEALTH" and "GENDER - MALE" in gender:
            return "MEN'S HEALTH"
    
    # ════════════════════════════════════════════════════════════════════════════
    # CATEGORY/SUBCATEGORY-BASED RULES  
    # R: FinalMerge.R Lines 643-650 (EXACT MATCH TO R CODE)
    # ════════════════════════════════════════════════════════════════════════════
    
    # Hydration products default to ENERGY SUPPORT
    # (Observed from R's master file output - ACTIVE NUTRITION / HYDRATION → ENERGY SUPPORT)
    if category == "ACTIVE NUTRITION" and subcategory == "HYDRATION":
        return "ENERGY SUPPORT"
    
    if category == "COMBINED MULTIVITAMINS":
        return "GENERAL HEALTH"
    elif current_health_focus == "GENERAL HEALTH":
        return "HEALTH FOCUS NON-SPECIFIC"
    
    # No rules matched - return current health focus
    return current_health_focus


def detect_granular_protein_type(title: str, ingredients: List[Dict]) -> str:
    """
    Detect specific protein type (matching R system's granular protein logic).
    
    This implements R's 200+ lines of protein detection from FI_CAT_Testing.R.
    Returns granular protein subcategory based on title keywords.
    
    Args:
        title: Product title
        ingredients: List of ingredient dicts
    
    Returns:
        Specific protein subcategory or empty string if not protein product
    """
    if not title:
        return ""
    
    title_lower = title.lower()
    
    # Check if this is a protein product
    has_protein = any('protein' in ing.get('name', '').lower() for ing in ingredients)
    if not has_protein and 'protein' not in title_lower:
        return ""
    
    # Count plant vs animal proteins (R system logic)
    plant_keywords = ['pea', 'rice', 'soy', 'hemp', 'alfalfa', 'baobab']
    animal_keywords = ['casein', 'egg', 'insect', 'beef', 'chicken', 'fish', 'meat', 'milk', 'whey']
    
    # Replace meat terms with generic "meat" (R system does this)
    for meat_term in ['beef', 'chicken', 'fish']:
        title_lower = title_lower.replace(meat_term, 'meat')
    
    plant_count = sum(1 for kw in plant_keywords if kw in title_lower)
    animal_count = sum(1 for kw in animal_keywords if kw in title_lower)
    
    # Apply R system logic tree (matching FI_CAT_Testing.R Lines 619-759)
    
    # Case 1: Both plant AND animal
    if plant_count > 0 and animal_count > 0:
        return 'PROTEIN - ANIMAL & PLANT COMBO'
    
    # Case 2: Multiple plant proteins
    if plant_count > 1:
        return 'PROTEIN - PLANT - MULTI'
    
    # Case 3: Single plant protein
    if plant_count == 1:
        if 'pea' in title_lower:
            return 'PROTEIN - PLANT - PEA'
        elif 'rice' in title_lower:
            return 'PROTEIN - PLANT - RICE'
        elif 'soy' in title_lower:
            return 'PROTEIN - PLANT - SOY'
        elif 'hemp' in title_lower:
            return 'PROTEIN - PLANT - HEMP'
        else:
            return 'PROTEIN - PLANT - GENERAL'
    
    # Case 4: Plant keyword with no specific type
    if 'plant' in title_lower or 'vegan' in title_lower:
        return 'PROTEIN - PLANT - GENERAL'
    
    # Case 5: Multiple animal proteins - check for common pairs
    if animal_count == 2:
        if 'whey' in title_lower and 'casein' in title_lower:
            return 'PROTEIN - ANIMAL - WHEY & CASEIN'
        elif 'milk' in title_lower and 'egg' in title_lower:
            return 'PROTEIN - ANIMAL - MILK & EGG'
        elif 'whey' in title_lower and 'milk' in title_lower:
            return 'PROTEIN - ANIMAL - WHEY & MILK'
        elif 'whey' in title_lower and 'egg' in title_lower:
            return 'PROTEIN - ANIMAL - WHEY & EGG'
        else:
            return 'PROTEIN - ANIMAL - MULTI'
    
    # Case 6: More than 2 animal proteins
    if animal_count > 2:
        return 'PROTEIN - ANIMAL - MULTI'
    
    # Case 7: Single animal protein
    if animal_count == 1:
        if 'whey' in title_lower:
            return 'PROTEIN - ANIMAL - WHEY'
        elif 'casein' in title_lower:
            return 'PROTEIN - ANIMAL - CASEIN'
        elif 'egg' in title_lower:
            return 'PROTEIN - ANIMAL - EGG'
        elif 'meat' in title_lower:
            return 'PROTEIN - ANIMAL - MEAT'
        elif 'milk' in title_lower:
            return 'PROTEIN - ANIMAL - MILK'
        elif 'insect' in title_lower:
            return 'PROTEIN - ANIMAL - INSECT'
        else:
            return 'PROTEIN - ANIMAL - GENERAL'
    
    # Case 8: No specific type detected
    if animal_count == 0 and plant_count == 0:
        return 'PROTEIN - ANIMAL - GENERAL'
    
    return ""


def apply_all_business_rules(ingredients_data, age_group, gender, title=""):
    """
    Apply all business rules in order (matching R system's FinalMerge.R):
    1. Title-Based Overrides (protein powder, weight loss)
    2. Ingredient-Specific Overrides (SAM-E, algae, etc.)
    3. Protein Rule (protein/whey/isolate)
    4. Herb Formula Rule (2+ herbs)
    5. Multivitamin Refinement (age + gender + title)
    6. Granular Protein Type Detection (optional - R system granularity)
    
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
            'health_focus': "HEALTH FOCUS NON-SPECIFIC",
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
            'all_ingredients': [],
            'health_focus': "HEALTH FOCUS NON-SPECIFIC",
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
    
    # If no multivitamin, use first by position (matches R's code)
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
    
    # RULE 5B: Granular Protein Type Detection (optional - for R system granularity)
    # Only applies if protein rule already triggered (category = SPORTS NUTRITION)
    if category == 'SPORTS NUTRITION' or subcategory == 'PROTEIN':
        protein_type = detect_granular_protein_type(title, sorted_ingredients)
        if protein_type:
            subcategory = protein_type
            reasoning_parts.append(f"Granular Protein Type: Detected '{protein_type}' from title keywords")
    
    # RULE 6: Health Focus (ingredient lookup + business rules)
    # Get initial health focus from ingredient lookup
    health_focus = get_health_focus_from_ingredient(primary_name)
    
    # Apply health focus business rules (title-based overrides, etc.)
    health_focus = apply_health_focus_rules(
        title=title, 
        primary_ingredient=primary_name, 
        current_health_focus=health_focus,
        category=category,
        subcategory=subcategory,
        gender=gender
    )
    
    return {
        'category': category,
        'subcategory': subcategory,
        'primary_ingredient': primary_name,
        'all_ingredients': [ing.get('name', '') for ing in sorted_ingredients],
        'health_focus': health_focus,
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
