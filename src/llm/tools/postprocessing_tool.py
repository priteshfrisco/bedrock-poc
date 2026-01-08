"""
Post-Processing Tool - LLM-callable tool for final processing

This tool is called by the LLM after business rules to:
1. Enforce ingredient combos (Glucosamine+Chondroitin, B vitamins, A+D)
2. Re-apply business rules (in case combos changed primary ingredient)
3. Assign health focus
4. Assign high-level category

This ensures the LLM can generate reasoning based on FINAL values.
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from src.pipeline.utils.business_rules import apply_all_business_rules
from src.llm.tools.health_focus_lookup import lookup_health_focus
from src.pipeline.utils.high_level_category import assign_high_level_category


def load_postprocessing_rules():
    """Load post-processing rules from JSON file"""
    # Go from src/llm/tools/ up to workspace root, then into reference_data/
    rules_path = Path(__file__).parent.parent.parent.parent / 'reference_data' / 'postprocessing_rules.json'
    with open(rules_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def detect_ingredient_combos(ingredients: List[Dict]) -> List[Dict]:
    """
    Detect and merge ingredient combinations based on rules from postprocessing_rules.json.
    
    This implements R's combo detection logic using configurable JSON rules:
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
    
    # Load combo rules from JSON
    rules = load_postprocessing_rules()
    combo_rules = rules['ingredient_combos']['combos']
    
    ingredient_names = [ing.get('name', '').upper() for ing in ingredients]
    modified = ingredients.copy()
    
    # Process each combo rule
    for combo_rule in combo_rules:
        combo_name = combo_rule['combo_name']
        required = [req.upper() for req in combo_rule['required_ingredients']]
        match_mode = combo_rule.get('match_mode', 'contains')
        condition = combo_rule.get('condition', None)
        merge_action = combo_rule['merge_action']
        
        # Check if all required ingredients are present
        if match_mode == 'contains':
            has_all = all(
                any(req in name for name in ingredient_names)
                for req in required
            )
        else:  # exact match
            has_all = all(req in ingredient_names for req in required)
        
        if not has_all:
            continue
        
        # Check condition if specified
        if condition == 'no_other_vitamins':
            # Get all vitamin ingredients excluding the combo ingredients
            other_vitamins = [
                name for name in ingredient_names 
                if 'VITAMIN' in name 
                and not any(req in name for req in required)
            ]
            if other_vitamins:
                continue  # Skip this combo if other vitamins present
        
        # All conditions met - merge the combo
        # Find first matching ingredient
        first_idx = None
        for i, ing in enumerate(modified):
            if any(req in ing.get('name', '').upper() for req in required):
                first_idx = i
                break
        
        if first_idx is not None:
            # Replace first ingredient with combo
            modified[first_idx]['name'] = combo_name
            modified[first_idx]['nw_category'] = merge_action['combo_category']
            modified[first_idx]['nw_subcategory'] = merge_action['combo_subcategory']
            
            # Remove other ingredients in the combo (but keep the one we just modified)
            modified = [
                ing for idx, ing in enumerate(modified)
                if idx == first_idx or not any(
                    req in ing.get('name', '').upper() 
                    for req in required
                )
            ]
    
    return modified


def apply_postprocessing_tool(
    ingredients: List[Dict],
    age_group: str,
    gender: str,
    title: str
) -> Dict[str, Any]:
    """
    Apply final post-processing steps and return complete results.
    
    This tool should be called AFTER apply_business_rules() to get the
    FINAL category, subcategory, health focus, and high-level category.
    
    Steps performed:
    1. Detect and merge ingredient combos (3 specific combos)
    2. Re-apply business rules with merged ingredients
    3. Lookup health focus for primary ingredient
    4. Assign high-level category
    
    Args:
        ingredients: List of ingredient dicts from lookup_ingredient calls
        age_group: Extracted age group
        gender: Extracted gender
        title: Product title
    
    Returns:
        Dict with:
        - ingredients_before_combo: Original ingredients list
        - ingredients_after_combo: Ingredients after combo detection
        - combo_detected: Boolean - true if combos were merged
        - combos_applied: List of combo names that were merged
        - final_category: Category after combo re-processing
        - final_subcategory: Subcategory after combo re-processing
        - primary_ingredient: Final primary ingredient (may be combo)
        - health_focus: Health focus category
        - high_level_category: PRIORITY VMS / NON-PRIORITY VMS / OTC / REMOVE
        - category_changed: Boolean - true if category changed due to combo
        - reasoning_context: Summary of changes for LLM reasoning
    """
    
    # Store original ingredients
    ingredients_before = [ing.copy() for ing in ingredients]
    
    # Step 1: Detect and merge ingredient combos
    ingredients_after = detect_ingredient_combos(ingredients)
    
    # Detect what combos were applied
    combos_applied = []
    combo_detected = len(ingredients_after) < len(ingredients_before)
    
    if combo_detected:
        # Check which combos were created
        combo_names = [ing.get('name', '') for ing in ingredients_after]
        
        if 'GLUCOSAMINE CHONDROITIN COMBO' in combo_names:
            combos_applied.append('Glucosamine + Chondroitin')
        if 'VITAMIN B1 - B2 - B6 - B12' in combo_names:
            combos_applied.append('B Vitamin Complex')
        if 'VITAMIN A & D COMBO' in combo_names:
            combos_applied.append('Vitamin A + D')
    
    # Step 2: Apply business rules with combo-merged ingredients
    business_result = apply_all_business_rules(ingredients_after, age_group, gender, title)
    
    final_category = business_result['category']
    final_subcategory = business_result['subcategory']
    primary_ingredient = business_result['primary_ingredient']
    
    # Step 3: Lookup health focus
    if primary_ingredient and primary_ingredient != 'N/A':
        hf_result = lookup_health_focus(primary_ingredient)
        health_focus = hf_result['health_focus'] if hf_result['found'] else 'UNKNOWN'
    else:
        health_focus = 'UNKNOWN'
    
    # Step 4: Assign high-level category
    high_level_category = assign_high_level_category(final_category)
    
    # Build reasoning context
    reasoning_parts = []
    
    if combo_detected:
        combo_str = ', '.join(combos_applied)
        reasoning_parts.append(f"Ingredient combo detected and merged: {combo_str}")
    
    if final_category:
        reasoning_parts.append(f"Final classification: {final_category} / {final_subcategory}")
    
    if health_focus and health_focus != 'UNKNOWN':
        reasoning_parts.append(f"Health focus: {health_focus}")
    
    reasoning_parts.append(f"High-level category: {high_level_category}")
    
    reasoning_context = " | ".join(reasoning_parts)
    
    return {
        'ingredients_before_combo': [ing.get('name', '') for ing in ingredients_before],
        'ingredients_after_combo': [ing.get('name', '') for ing in ingredients_after],
        'combo_detected': combo_detected,
        'combos_applied': combos_applied,
        'final_category': final_category,
        'final_subcategory': final_subcategory,
        'primary_ingredient': primary_ingredient,
        'all_ingredients': business_result['all_ingredients'],
        'health_focus': health_focus,
        'high_level_category': high_level_category,
        'category_changed': combo_detected,  # Combos may change category
        'reasoning_context': reasoning_context,
        'full_ingredients_data': ingredients_after  # Full ingredient objects for audit
    }


# Tool definition for OpenAI function calling
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "apply_postprocessing",
        "description": (
            "Apply final post-processing to get complete results. "
            "Call this AFTER apply_business_rules() to: "
            "1) Detect and merge ingredient combos (Glucosamine+Chondroitin, B vitamins, A+D), "
            "2) Get final category/subcategory with combos applied, "
            "3) Get health focus assignment, "
            "4) Get high-level category classification. "
            "Use the results from this tool to provide your final reasoning."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ingredients": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "position": {"type": "number"},
                            "category": {"type": "string"},
                            "subcategory": {"type": "string"}
                        }
                    },
                    "description": "Array of ingredient objects from lookup_ingredient calls"
                },
                "age_group": {
                    "type": "string",
                    "description": "Extracted age group value"
                },
                "gender": {
                    "type": "string",
                    "description": "Extracted gender value"
                },
                "title": {
                    "type": "string",
                    "description": "Product title"
                }
            },
            "required": ["ingredients", "age_group", "gender", "title"]
        }
    }
}


if __name__ == '__main__':
    # Test the tool with combo detection
    test_ingredients = [
        {
            "name": "GLUCOSAMINE",
            "position": 1,
            "category": "JOINT HEALTH",
            "subcategory": "GLUCOSAMINE"
        },
        {
            "name": "CHONDROITIN",
            "position": 2,
            "category": "JOINT HEALTH",
            "subcategory": "CHONDROITIN"
        },
        {
            "name": "MSM",
            "position": 3,
            "category": "JOINT HEALTH",
            "subcategory": "MSM"
        }
    ]
    
    result = apply_postprocessing_tool(
        ingredients=test_ingredients,
        age_group="AGE GROUP - NON SPECIFIC",
        gender="GENDER - NON SPECIFIC",
        title="Glucosamine Chondroitin MSM 120 Tablets"
    )
    
    print("Post-Processing Result:")
    print(f"  Combo Detected: {result['combo_detected']}")
    print(f"  Combos Applied: {result['combos_applied']}")
    print(f"  Before: {result['ingredients_before_combo']}")
    print(f"  After: {result['ingredients_after_combo']}")
    print(f"  Final Category: {result['final_category']}")
    print(f"  Final Subcategory: {result['final_subcategory']}")
    print(f"  Primary: {result['primary_ingredient']}")
    print(f"  Health Focus: {result['health_focus']}")
    print(f"  High-Level Category: {result['high_level_category']}")
    print(f"  Reasoning Context: {result['reasoning_context']}")

