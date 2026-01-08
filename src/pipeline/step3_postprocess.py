"""
Step 3: Post-Processing - Apply business rules, health focus, and high-level category
"""

from typing import Dict, List, Any
from src.pipeline.utils.business_rules import apply_all_business_rules
from src.llm.tools.health_focus_lookup import lookup_health_focus
from src.pipeline.utils.high_level_category import assign_high_level_category
from src.core.log_manager import LogManager


def detect_ingredient_combos(ingredients: List[Dict]) -> List[Dict]:
    """
    Detect and merge ingredient combinations (matching R system behavior).
    
    This implements R's combo detection logic from FinalMerge.R:
    - Glucosamine + Chondroitin → GLUCOSAMINE CHONDROITIN COMBO
    - B1 + B2 + B6 + B12 (no other vitamins) → VITAMIN B1 - B2 - B6 - B12
    - Vitamin A + D (no other vitamins) → VITAMIN A & D COMBO
    
    Args:
        ingredients: List of ingredient dicts with name, position, category, subcategory
    
    Returns:
        Modified ingredients list with combos merged
    """
    if not ingredients:
        return ingredients
    
    ingredient_names = [ing.get('name', '').upper() for ing in ingredients]
    modified = ingredients.copy()
    
    # Combo 1: Glucosamine + Chondroitin
    has_glucosamine = any('GLUCOSAMINE' in name for name in ingredient_names)
    has_chondroitin = any('CHONDROITIN' in name for name in ingredient_names)
    
    if has_glucosamine and has_chondroitin:
        # Find indices
        gluc_idx = next(i for i, ing in enumerate(modified) if 'GLUCOSAMINE' in ing.get('name', '').upper())
        chon_idx = next(i for i, ing in enumerate(modified) if 'CHONDROITIN' in ing.get('name', '').upper())
        
        # Replace glucosamine with combo
        modified[gluc_idx]['name'] = 'GLUCOSAMINE CHONDROITIN COMBO'
        modified[gluc_idx]['nw_category'] = 'JOINT HEALTH'
        modified[gluc_idx]['nw_subcategory'] = 'GLUCOSAMINE & CHONDROITIN'
        
        # Remove chondroitin (adjust index if chondroitin comes before glucosamine)
        if chon_idx > gluc_idx:
            modified.pop(chon_idx)
        else:
            modified.pop(chon_idx)
            # Adjust glucosamine index since we removed an element before it
            if gluc_idx > chon_idx:
                gluc_idx -= 1
    
    # Combo 2: Vitamin B1 + B2 + B6 + B12 (only if NO other vitamins)
    b_vitamins = ['VITAMIN B1', 'VITAMIN B2', 'VITAMIN B6', 'VITAMIN B12']
    has_all_b_vitamins = all(any(b_vit in name for name in ingredient_names) for b_vit in b_vitamins)
    
    if has_all_b_vitamins:
        # Check if there are OTHER vitamins
        other_vitamins = [name for name in ingredient_names 
                         if 'VITAMIN' in name 
                         and not any(b_vit in name for b_vit in b_vitamins)]
        
        if not other_vitamins:  # No other vitamins, safe to merge
            # Find first B vitamin index
            b1_idx = next((i for i, ing in enumerate(modified) if 'VITAMIN B1' in ing.get('name', '').upper()), None)
            
            if b1_idx is not None:
                # Replace with combo
                modified[b1_idx]['name'] = 'VITAMIN B1 - B2 - B6 - B12'
                modified[b1_idx]['nw_category'] = 'BASIC VITAMINS & MINERALS'
                modified[b1_idx]['nw_subcategory'] = 'LETTER VITAMINS'
                
                # Remove other B vitamins (B2, B6, B12)
                modified = [ing for ing in modified 
                           if not any(b_vit in ing.get('name', '').upper() 
                                    for b_vit in b_vitamins[1:])]
    
    # Combo 3: Vitamin A + D (only if NO other vitamins)
    has_vitamin_a = any('VITAMIN A' in name and 'VITAMIN A' == name.split()[0] + ' ' + name.split()[1] for name in ingredient_names)
    has_vitamin_d = any('VITAMIN D' in name for name in ingredient_names)
    
    if has_vitamin_a and has_vitamin_d:
        # Check if there are OTHER vitamins
        other_vitamins = [name for name in ingredient_names 
                         if 'VITAMIN' in name 
                         and 'VITAMIN A' not in name 
                         and 'VITAMIN D' not in name]
        
        if not other_vitamins:  # No other vitamins, safe to merge
            # Find vitamin A
            vit_a_idx = next((i for i, ing in enumerate(modified) if 'VITAMIN A' in ing.get('name', '').upper()), None)
            
            if vit_a_idx is not None:
                # Replace with combo
                modified[vit_a_idx]['name'] = 'VITAMIN A & D COMBO'
                modified[vit_a_idx]['nw_category'] = 'BASIC VITAMINS & MINERALS'
                modified[vit_a_idx]['nw_subcategory'] = 'LETTER VITAMINS'
                
                # Remove vitamin D
                modified = [ing for ing in modified if 'VITAMIN D' not in ing.get('name', '').upper()]
    
    return modified


def apply_postprocessing(
    ingredients: List,
    age: str,
    gender: str,
    title: str,
    asin: str,
    log_manager: LogManager
) -> Dict[str, Any]:
    """
    Apply business rules, health focus lookup, and high-level category assignment
    
    Args:
        ingredients: List of extracted ingredients
        age: Extracted age value
        gender: Extracted gender value
        title: Product title
        asin: Product ASIN
        log_manager: Log manager instance
    
    Returns:
        Dict with category, subcategory, primary_ingredient, health_focus, high_level_category
    """
    
    log_manager.log_step('step3_postprocess', f"[{asin}] Applying business rules...")
    
    # Detect and merge ingredient combos (R system behavior)
    ingredients = detect_ingredient_combos(ingredients)
    
    # Apply business rules
    business_result = apply_all_business_rules(ingredients, age, gender, title)
    category = business_result['category']
    subcategory = business_result['subcategory']
    primary_ingredient = business_result['primary_ingredient']
    
    log_manager.log_step(
        'step3_postprocess',
        f"[{asin}] Category: {category}, Subcategory: {subcategory}, Primary: {primary_ingredient}"
    )
    
    # Lookup health focus for primary ingredient
    if primary_ingredient and primary_ingredient != 'N/A':
        hf_result = lookup_health_focus(primary_ingredient)
        health_focus = hf_result['health_focus'] if hf_result['found'] else 'UNKNOWN'
        log_manager.log_step('step3_postprocess', f"[{asin}] Health Focus: {health_focus}")
    else:
        health_focus = 'UNKNOWN'
    
    # Assign high-level category
    high_level_category = assign_high_level_category(category)
    log_manager.log_step('step3_postprocess', f"[{asin}] High Level Category: {high_level_category}")
    
    return {
        'category': category,
        'subcategory': subcategory,
        'primary_ingredient': primary_ingredient,
        'health_focus': health_focus,
        'high_level_category': high_level_category
    }

