#!/usr/bin/env python3
"""
Complete Prompt Builder - Shows the FULL prompt sent to LLM
"""

import json
import csv
from pathlib import Path
from collections import defaultdict


def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)


def load_non_supplement_keywords():
    """Load and group non-supplement keywords from CSV"""
    keywords_by_category = defaultdict(list)
    
    with open('reference_data/non_supplement_keywords.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row['keyword']:  # Skip empty rows
                continue
            
            category = row['category']
            keyword = row['keyword']
            exceptions = row['exceptions'].strip() if row['exceptions'] else None
            notes = row['notes'].strip() if row['notes'] else None
            
            keywords_by_category[category].append({
                'keyword': keyword,
                'exceptions': exceptions,
                'notes': notes
            })
    
    return keywords_by_category


def format_safety_check_section():
    """Build the safety check section dynamically from CSV"""
    keywords_by_category = load_non_supplement_keywords()
    
    # Auto-format category names: "body_care" → "Body Care"
    # Client can use any name they want in CSV (e.g., "Books/Media" directly)
    merged_categories = defaultdict(list)
    for cat, items in keywords_by_category.items():
        friendly_name = cat.replace('_', ' ').title()
        merged_categories[friendly_name].extend(items)
    
    # Build the text
    lines = ["Common non-supplement categories to watch for:"]
    
    for category_name in sorted(merged_categories.keys()):
        items = merged_categories[category_name]
        
        # Get all keywords without exceptions
        regular_keywords = [item['keyword'] for item in items if not item['exceptions']]
        
        # Get all keywords with exceptions
        exception_keywords = [item for item in items if item['exceptions']]
        
        # Format the category line
        if regular_keywords:
            keywords_str = ', '.join([f'"{kw}"' for kw in regular_keywords])
            lines.append(f"  • {category_name}: {keywords_str}")
        else:
            lines.append(f"  • {category_name}:")
        
        # Add exceptions inline
        for item in exception_keywords:
            exceptions_list = item['exceptions'].split(',')
            exceptions_str = '/'.join(exceptions_list)
            example = f" (e.g., \"{item['notes']}\")" if item['notes'] and 'e.g.' in item['notes'] else ""
            lines.append(f"    EXCEPT: \"{item['keyword']}\" + {exceptions_str} = Keep{example}")
    
    return '\n'.join(lines)


def build_complete_prompt(product_title: str):
    """Build the complete LLM prompt (brand not needed - R removes it before processing)"""
    
    # Load all files
    general_instructions = load_json('reference_data/general_instructions.json')
    age_rules = load_json('reference_data/age_extraction_rules.json')
    gender_rules = load_json('reference_data/gender_extraction_rules.json')
    form_rules = load_json('reference_data/form_extraction_rules.json')
    form_priority = load_json('reference_data/form_priority_rules.json')
    organic_rules = load_json('reference_data/organic_extraction_rules.json')
    count_rules = load_json('reference_data/pack_count_extraction_rules.json')
    unit_rules = load_json('reference_data/unit_extraction_rules.json')
    size_rules = load_json('reference_data/size_extraction_rules.json')
    potency_rules = load_json('reference_data/potency_extraction_rules.json')
    ingredient_rules = load_json('reference_data/ingredient_extraction_rules.json')
    business_rules = load_json('reference_data/business_rules.json')
    
    # Extract valid values from extraction rules (single source of truth)
    valid_age_groups = list(age_rules['keywords'].keys()) + [age_rules['default']]
    valid_genders = list(gender_rules['keywords'].keys()) + [gender_rules['default']]
    valid_forms = list(form_rules['keywords'].keys()) + [form_rules['default']]
    
    # Build safety check dynamically from CSV
    safety_check = format_safety_check_section()
    
    # System prompt
    system_prompt = "You are a supplement classification expert. Extract structured information from product titles step by step. Be accurate and precise. Only extract information that is present in the title."
    
    prompt = f"""
{system_prompt}

================================================================================
CRITICAL SAFETY CHECK - READ THIS FIRST!
================================================================================

{general_instructions['safety_warnings'].format(safety_check=safety_check)}

================================================================================
TASK: EXTRACT SUPPLEMENT ATTRIBUTES
================================================================================

{general_instructions['task_description']}

{general_instructions['false_positive_warnings']}

================================================================================
STEP 1: EXTRACT AGE
================================================================================

Instructions: {age_rules['instructions']}

Keywords to search for:
"""
    
    # Age keywords
    for value, keywords in age_rules['keywords'].items():
        prompt += f"  - {keywords} → {value}\n"
    prompt += f"\nDefault: {age_rules['default']}\n"
    prompt += f"Valid values: {valid_age_groups}\n\n"
    
    # Gender
    prompt += f"""
================================================================================
STEP 2: EXTRACT GENDER
================================================================================

Instructions: {gender_rules['instructions']}

Keywords to search for:
"""
    
    for value, keywords in gender_rules['keywords'].items():
        prompt += f"  - {keywords} → {value}\n"
    
    if 'special_rules' in gender_rules:
        prompt += "\nSpecial Rules:\n"
        for rule in gender_rules['special_rules']:
            prompt += f"  - {rule}\n"
    
    prompt += f"\nDefault: {gender_rules['default']}\n"
    prompt += f"Valid values: {valid_genders}\n\n"
    
    # Form
    prompt += f"""
================================================================================
STEP 3: EXTRACT FORM
================================================================================

Instructions: {form_rules['instructions']}

STEP 3A: Search for form keywords (ALL {len(form_rules['keywords'])} form types):
"""
    
    for value, keywords in form_rules['keywords'].items():
        prompt += f"  - {keywords} → {value}\n"
    prompt += "\n"
    
    prompt += f"Default: {form_rules['default']}\n"
    prompt += f"Valid values: {valid_forms}\n\n"
    
    prompt += "STEP 3B: If multiple form keywords found, apply priority rules:\n\n"
    
    for rule in form_priority['rules']:
        prompt += f"[{rule['rule_id']}] Priority {rule['priority']}\n"
        prompt += f"  {rule['condition']}\n"
        prompt += f"  → {rule['action']}\n"
        prompt += f"  Reason: {rule['reason']}\n\n"
    
    # Organic
    prompt += f"""
================================================================================
STEP 4: EXTRACT ORGANIC STATUS
================================================================================

Instructions: {organic_rules['instructions']}

Priority Order (check in this order):
"""
    
    for rule in organic_rules['priority_order']:
        prompt += f"{rule['priority']}. Keywords: {rule['keywords']} → Result: {rule['result']}\n"
        prompt += f"   Reason: {rule['reason']}\n"
    
    prompt += f"\nDefault: {organic_rules['default']}\n"
    prompt += f"\nEdge Case Example: {organic_rules['edge_case_example']}\n"
    
    # Count
    prompt += f"""
================================================================================
STEP 5: EXTRACT COUNT
================================================================================

Instructions: {count_rules['instructions']}

Pack Count Indicators (look for numbers BEFORE these keywords):
"""
    
    for keyword in count_rules['keywords']['pack_indicators']:
        prompt += f"  - {keyword}\n"
    
    prompt += f"\nDefault: {count_rules['default']}\n\n"
    
    # Add examples from JSON
    prompt += "Examples:\n"
    for example in count_rules['examples']:
        prompt += f"  • \"{example['title']}\" → Pack Count = {example['pack_count']}\n"
        prompt += f"    ({example['reasoning']})\n"
    prompt += "\n"
    
    prompt += "⚠️  CRITICAL WARNINGS:\n"
    for warning in count_rules['warnings']:
        prompt += f"  {warning}\n"
    
    # Unit of Measurement
    prompt += f"""

================================================================================
STEP 6: EXTRACT UNIT OF MEASUREMENT
================================================================================

Instructions: {unit_rules['instructions']}

DISCRETE UNITS → Return 'COUNT':
  {', '.join(unit_rules['unit_types']['discrete_units']['indicators'][:10])}...

VOLUME UNITS → Return 'oz':
  {', '.join(unit_rules['unit_types']['volume_units']['indicators'])}

WEIGHT UNITS → Return base form:
"""
    
    for unit_base, variants in unit_rules['unit_types']['weight_units']['indicators'].items():
        prompt += f"  - {', '.join(variants)} → '{unit_base}'\n"
    
    prompt += f"\nDefault: {unit_rules['default']}\n\n"
    
    # Add examples from JSON
    prompt += "Examples:\n"
    for example in unit_rules['examples']:
        prompt += f"  • \"{example['title']}\" → {example['unit']}\n"
        prompt += f"    ({example['reasoning']})\n"
    prompt += "\n"
    
    # Size (Pack Size)
    prompt += f"""
================================================================================
STEP 7: EXTRACT SIZE (PACK SIZE)
================================================================================

Instructions: {size_rules['instructions']}

Size Indicators (keywords that indicate quantity):
"""
    
    for keyword in size_rules['keywords']['size_indicators']:
        prompt += f"  - {keyword}\n"
    
    prompt += "\nVolume Indicators:\n"
    for keyword in size_rules['keywords']['volume_indicators']:
        prompt += f"  - {keyword}\n"
    
    prompt += "\nWeight Indicators:\n"
    for keyword in size_rules['keywords']['weight_indicators']:
        prompt += f"  - {keyword}\n"
    
    prompt += f"\nDefault: {size_rules['default']}\n\n"
    
    # Add examples from JSON
    prompt += "Examples:\n"
    for example in size_rules['examples']:
        prompt += f"  • \"{example['title']}\" → {example['size']}\n"
        prompt += f"    ({example['reasoning']})\n"
    prompt += "\n"
    
    prompt += "⚠️  CRITICAL WARNINGS:\n"
    for warning in size_rules['warnings']:
        prompt += f"  {warning}\n"
    
    # Functional Ingredient Extraction (STEP 8 - must come before potency!)
    prompt += f"""

================================================================================
STEP 8: EXTRACT FUNCTIONAL INGREDIENTS
================================================================================

⚠️  NOTE: Extract potency AFTER identifying ingredients, so you know which is primary!

Instructions: {ingredient_rules['instructions']}

⚠️  CRITICAL RULES - READ CAREFULLY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    for rule in ingredient_rules.get('critical_rules', []):
        prompt += f"{rule}\n"
    
    # Add exclusions section if present
    if 'exclusions' in ingredient_rules:
        exclusions = ingredient_rules['exclusions']
        prompt += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  EXCLUSIONS - DO NOT EXTRACT THESE AS INGREDIENTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{exclusions['description']}

FLAVOR KEYWORDS TO EXCLUDE (unless clearly functional ingredients):
{', '.join(exclusions['flavor_keywords'])}

INSTRUCTIONS:
"""
        for instruction in exclusions['instructions']:
            prompt += f"  • {instruction}\n"
        
        prompt += "\nEXAMPLES:\n"
        for example in exclusions['examples']:
            prompt += f"  Title: \"{example['title']}\"\n"
            prompt += f"    ✅ Extract: {example['extract']}\n"
            prompt += f"    ❌ Skip: {example['skip']}\n"
            prompt += f"    Reason: {example['reason']}\n\n"
    
    # Load extraction steps, primary ingredient logic, and tool calling from JSON
    prompt += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXTRACTION STEPS:"""
    
    for step in ingredient_rules['extraction_steps']:
        prompt += f"\n{step}"
    
    prompt += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PRIMARY INGREDIENT DETERMINATION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULE: {ingredient_rules['primary_ingredient_logic']['rule']}

EXCEPTION: {ingredient_rules['primary_ingredient_logic']['exception']}

PRIMARY INGREDIENT KEYWORDS:
• Multivitamin: {', '.join(ingredient_rules['special_cases']['multivitamin']['keywords'])}
• Protein: {', '.join(ingredient_rules['special_cases']['protein']['keywords'])}

TOOL CALLING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For EACH ingredient found, you MUST call: {ingredient_rules['tool_calling']['tool_name']}(ingredient_name="[name]")

⚠️  CRITICAL - {ingredient_rules['tool_calling']['critical_note']}

✅ CORRECT EXAMPLES:
"""
    for example in ingredient_rules['tool_calling']['correct_examples']:
        prompt += f"  {example}\n"
    
    prompt += "\n❌ WRONG - DO NOT DO THIS:\n"
    for example in ingredient_rules['tool_calling']['wrong_examples']:
        prompt += f"  {example}\n"
    
    prompt += f"""
{ingredient_rules['tool_calling']['note']}

The tool returns: {', '.join(ingredient_rules['tool_calling']['response'].keys())}

SPECIAL HANDLING FOR PROBIOTICS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{ingredient_rules['special_handling']['probiotics']['description']}

Example:
  Title: "{ingredient_rules['special_handling']['probiotics']['example']['title']}"
  {ingredient_rules['special_handling']['probiotics']['example']['step_1']}
  {ingredient_rules['special_handling']['probiotics']['example']['step_2']}

SPECIAL HANDLING FOR COMBO PRODUCTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{ingredient_rules['special_handling']['combo_products']['description']}

Example:
  Title: "{ingredient_rules['special_handling']['combo_products']['example']['title']}"
  ✅ CORRECT: {ingredient_rules['special_handling']['combo_products']['example']['correct_approach']}
  
  ❌ WRONG: {ingredient_rules['special_handling']['combo_products']['example']['wrong_approach']}

⚠️  CRITICAL: {ingredient_rules['special_handling']['normalized_names']['critical_note']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{ingredient_rules['special_handling']['normalized_names']['description']}

❌ WRONG:
  {{
    "name": "{ingredient_rules['special_handling']['normalized_names']['wrong_example']['name']}",  ← {ingredient_rules['special_handling']['normalized_names']['wrong_example']['note']}
    ...
  }}

✅ CORRECT:
  {{
    "name": "{ingredient_rules['special_handling']['normalized_names']['correct_example']['name']}",  ← {ingredient_rules['special_handling']['normalized_names']['correct_example']['note']}
    ...
  }}

OUTPUT FORMAT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{ingredient_rules['output_format']['description']}

Example: {ingredient_rules['output_format']['example']}

⚠️  CRITICAL RULES:
"""
    for rule in ingredient_rules['output_format']['critical_rules']:
        prompt += f"- {rule}\n"
    
    prompt += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
================================================================================
STEP 9: EXTRACT POTENCY (DOSAGE/STRENGTH)
================================================================================

{potency_rules.get('context_reminder', '')}

Instructions: {potency_rules['instructions']}

Priority Order (check in this order):
"""
    
    for rule in potency_rules['priority_order']:
        prompt += f"{rule['priority']}. {rule['name']}\n"
        prompt += f"   Examples: {', '.join(rule['pattern_examples'])}\n"
        prompt += f"   Unit: {rule['unit']}\n"
        prompt += f"   Extraction: {rule['extraction']}\n\n"
    
    prompt += "\n⚠️  CRITICAL RULES:\n"
    for rule in potency_rules['critical_rules']:
        prompt += f"{rule}\n"
    
    prompt += "\nExamples:\n"
    for example in potency_rules['examples'][:5]:  # Show first 5 examples
        prompt += f"Title: \"{example['title']}\"\n"
        prompt += f"→ Primary Ingredient: {example['primary_ingredient']}\n"
        prompt += f"→ Potency: \"{example['potency']}\"\n"
        prompt += f"   Reasoning: {example['reasoning']}\n\n"
    
    prompt += f"Default: \"{potency_rules['default']}\" ({potency_rules['default_reasoning']})\n"
    
    # Potency Extraction (STEP 9 - must come after ingredients!)
    prompt += f"""


================================================================================
STEP 10: APPLY BUSINESS RULES
================================================================================

🔧 CRITICAL: After extracting all ingredients, you MUST call apply_business_rules()

This tool applies deterministic business rules to determine the final category
and subcategory. It handles:
- Primary ingredient selection (first by position, or multivitamin override)
- Title-based overrides (protein powder, weight loss, etc.)
- Ingredient-specific overrides (CoQ10, SAM-E, algae, probiotics)
- Protein rules (whey, isolate, casein)
- Herb formula rules (2+ herbs = FORMULAS, 1 herb = SINGLES)
- Multivitamin refinement (age + gender subcategory logic)

CALL THE TOOL:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  apply_business_rules(
    ingredients=[...all ingredient objects from lookup_ingredient calls...],
    age_group="[the age value you extracted]",
    gender="[the gender value you extracted]",
    title="[the product title]"
  )

The tool will return:
- initial_category: Category from primary ingredient lookup (BEFORE business rules)
- initial_subcategory: Subcategory from primary ingredient lookup (BEFORE business rules)
- final_category: Final category AFTER business rules
- final_subcategory: Final subcategory AFTER business rules
- primary_ingredient: Name of primary ingredient
- changes_made: Array of changes (e.g., "Category: X → Y")
- has_changes: Boolean (true if category/subcategory changed)
- has_unknown: Boolean (true if contains UNKNOWN values)
- should_explain: Boolean (true if you should provide reasoning)
- reasoning_context: What changed and why (use this for your reasoning)

REASONING INSTRUCTIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  CRITICAL: Only provide reasoning when should_explain is TRUE!

When should_explain is TRUE, write a brief explanation (1-2 sentences) based on:
- reasoning_context: Contains what changed and why
- changes_made: Shows before → after for category/subcategory
- has_unknown: If true, explain that ingredient wasn't found in database

Examples of GOOD reasoning:
✅ "CoQ10 triggered subcategory override from MINERALS to COENZYME Q10"
✅ "Multivitamin refined to WOMEN MATURE based on female gender and mature adult age"
✅ "Title contains 'protein powder' which overrode category to ACTIVE NUTRITION"
✅ "Primary ingredient not found in database, category set to UNKNOWN"

Examples of BAD reasoning (don't do this):
❌ "Standard processing" (don't provide reasoning if should_explain is FALSE)
❌ "Category is LETTER VITAMINS" (just stating the result, not explaining changes)
❌ "Applied business rules" (too vague)

When should_explain is FALSE:
- Leave reasoning field NULL or empty string
- This means no significant changes occurred (standard processing)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    prompt += f"""
================================================================================
OUTPUT FORMAT
================================================================================

{general_instructions['output_format_instructions']}

================================================================================
PRODUCT TO CLASSIFY
================================================================================

{general_instructions['formatting_issues_warning']}

"""
    prompt += f'Title: "{product_title}"\n\n'
    
    prompt += f"""{general_instructions['workflow_instructions']}
"""
    
    return prompt


if __name__ == '__main__':
    # Test with example product
    example_title = "Women's 50+ Multivitamin with Turmeric Powder in Vegetable Capsules"
    
    print(build_complete_prompt(example_title))
    
    print("\n" + "="*80)
    print("PROMPT LENGTH:", len(build_complete_prompt(example_title)), "characters")


