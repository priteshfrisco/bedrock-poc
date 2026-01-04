"""
Step 3: Post-Processing - Apply business rules, health focus, and high-level category
"""

from typing import Dict, List, Any
from src.pipeline.utils.business_rules import apply_all_business_rules
from src.llm.tools.health_focus_lookup import lookup_health_focus
from src.pipeline.utils.high_level_category import assign_high_level_category
from src.core.log_manager import LogManager


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

