"""
Business Rules Tool - LLM-callable tool for applying business rules

This tool is called by the LLM after ingredient extraction to apply
all business rules and determine final category/subcategory.
"""

from typing import Dict, List, Any
from src.pipeline.utils.business_rules import apply_all_business_rules


def apply_business_rules_tool(
    ingredients: List[Dict],
    age_group: str,
    gender: str,
    title: str
) -> Dict[str, Any]:
    """
    Apply all business rules to determine final category and subcategory.
    
    This is called by the LLM after extracting ingredients and looking them up.
    The business rules are deterministic Python logic that applies overrides
    based on ingredients, age, gender, and title keywords.
    
    Args:
        ingredients: List of ingredient dicts with lookup results
        age_group: Extracted age group (e.g., "AGE GROUP - ADULT")
        gender: Extracted gender (e.g., "GENDER - FEMALE")
        title: Product title for title-based overrides
    
    Returns:
        Dict with:
        - initial_category: Category from primary ingredient lookup (BEFORE rules)
        - initial_subcategory: Subcategory from primary ingredient lookup (BEFORE rules)
        - final_category: Final category after business rules
        - final_subcategory: Final subcategory after business rules
        - primary_ingredient: Name of primary ingredient
        - all_ingredients: List of all ingredient names
        - rules_applied: Array of rule descriptions (for reasoning)
        - changes_made: Array of specific changes (e.g., "Category: X → Y")
        - has_changes: Boolean indicating if any changes were made
        - should_explain: Boolean - true if reasoning should be provided
    """
    
    # Apply business rules
    result = apply_all_business_rules(ingredients, age_group, gender, title)
    
    # Parse reasoning to extract initial and final values
    reasoning_text = result.get('reasoning', '')
    rules_applied = reasoning_text.split(' | ') if reasoning_text else []
    
    # Extract initial category/subcategory from reasoning
    initial_category = None
    initial_subcategory = None
    for rule in rules_applied:
        if 'Initial Category/Subcategory:' in rule:
            parts = rule.replace('Initial Category/Subcategory:', '').strip().split('/')
            if len(parts) == 2:
                initial_category = parts[0].strip()
                initial_subcategory = parts[1].strip()
            break
    
    final_category = result['category']
    final_subcategory = result['subcategory']
    
    # Detect changes
    changes_made = []
    category_changed = initial_category and initial_category != final_category
    subcategory_changed = initial_subcategory and initial_subcategory != final_subcategory
    
    if category_changed:
        changes_made.append(f"Category changed: {initial_category} → {final_category}")
    if subcategory_changed:
        changes_made.append(f"Subcategory changed: {initial_subcategory} → {final_subcategory}")
    
    # Check for unknowns
    has_unknown = 'UNKNOWN' in str([final_category, final_subcategory])
    
    # Determine if changes are significant enough to explain
    has_overrides = any(
        'override' in rule.lower() or 
        'rule' in rule.lower()
        for rule in rules_applied
    )
    
    should_explain = (
        len(changes_made) > 0 or  # Any category/subcategory changes
        has_overrides or           # Business rule overrides applied
        has_unknown or             # Has UNKNOWN values
        len(rules_applied) > 2     # Multiple rules applied
    )
    
    # Generate brief summary for significant changes only
    reasoning_context = ""
    if should_explain:
        context_parts = []
        
        # Add change info
        if changes_made:
            context_parts.extend(changes_made)
        
        # Add override info
        significant_rules = [
            rule for rule in rules_applied 
            if 'override' in rule.lower() or 
               'rule' in rule.lower() or
               'refinement' in rule.lower()
        ]
        if significant_rules:
            context_parts.extend(significant_rules)
        
        # Add unknown context
        if has_unknown:
            context_parts.append("Contains UNKNOWN values - ingredient may not be in database")
        
        reasoning_context = " | ".join(context_parts)
    
    return {
        'initial_category': initial_category or final_category,
        'initial_subcategory': initial_subcategory or final_subcategory,
        'final_category': final_category,
        'final_subcategory': final_subcategory,
        'primary_ingredient': result['primary_ingredient'],
        'all_ingredients': result['all_ingredients'],
        'rules_applied': rules_applied,
        'changes_made': changes_made,
        'has_changes': len(changes_made) > 0 or has_overrides,
        'has_unknown': has_unknown,
        'should_explain': should_explain,
        'reasoning_context': reasoning_context,  # What the LLM should use for reasoning
        'full_reasoning': reasoning_text  # Keep full reasoning for audit
    }


# Tool definition for OpenAI function calling
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "apply_business_rules",
        "description": (
            "Apply business rules to determine final category and subcategory. "
            "Call this AFTER extracting all ingredients and looking them up. "
            "Returns BOTH initial values (from ingredient lookup) AND final values (after business rules), "
            "plus information about what changed. Use this information to provide reasoning "
            "ONLY when changes were made or UNKNOWN values are present."
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
                    "description": "Array of ingredient objects from lookup_ingredient calls, each with name, position, category, and subcategory"
                },
                "age_group": {
                    "type": "string",
                    "description": "Extracted age group value (e.g., 'AGE GROUP - ADULT', 'AGE GROUP - NON SPECIFIC')"
                },
                "gender": {
                    "type": "string",
                    "description": "Extracted gender value (e.g., 'GENDER - FEMALE', 'GENDER - NON SPECIFIC')"
                },
                "title": {
                    "type": "string",
                    "description": "Product title (for title-based override detection)"
                }
            },
            "required": ["ingredients", "age_group", "gender", "title"]
        }
    }
}


if __name__ == '__main__':
    # Test the tool
    test_ingredients = [
        {
            "name": "coq10",
            "position": 0,
            "category": "BASIC VITAMINS & MINERALS",
            "subcategory": "MINERALS"
        },
        {
            "name": "bioperine",
            "position": 15,
            "category": "FATTY ACIDS",
            "subcategory": "HEMP/CBD"
        }
    ]
    
    result = apply_business_rules_tool(
        ingredients=test_ingredients,
        age_group="AGE GROUP - NON SPECIFIC",
        gender="GENDER - NON SPECIFIC",
        title="CoQ10 with BioPerine 100mg"
    )
    
    print("Business Rules Result:")
    print(f"  Initial Category: {result['initial_category']}")
    print(f"  Initial Subcategory: {result['initial_subcategory']}")
    print(f"  Final Category: {result['final_category']}")
    print(f"  Final Subcategory: {result['final_subcategory']}")
    print(f"  Primary: {result['primary_ingredient']}")
    print(f"  Has Changes: {result['has_changes']}")
    print(f"  Has Unknown: {result['has_unknown']}")
    print(f"  Should Explain: {result['should_explain']}")
    print(f"  Reasoning Context: {result['reasoning_context']}")
    print(f"  Changes Made:")
    for change in result['changes_made']:
        print(f"    - {change}")

