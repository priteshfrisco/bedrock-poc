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
    prompts = load_json('src/llm/prompts.json')
    age_rules = load_json('reference_data/age_extraction_rules.json')
    gender_rules = load_json('reference_data/gender_extraction_rules.json')
    form_rules = load_json('reference_data/form_extraction_rules.json')
    form_priority = load_json('reference_data/form_priority_rules.json')
    organic_rules = load_json('reference_data/organic_extraction_rules.json')
    count_rules = load_json('reference_data/count_extraction_rules.json')
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
    
    prompt = f"""
{prompts['system_prompt']}

================================================================================
CRITICAL SAFETY CHECK - READ THIS FIRST!
================================================================================

⚠️  BEFORE EXTRACTING ATTRIBUTES, CHECK IF THIS IS A NON-SUPPLEMENT:

If the title appears to be a NON-SUPPLEMENT product (not a dietary supplement),
return "REMOVE" for all fields.

{safety_check}

✅ IMPORTANT: These ARE supplements (do NOT mark as REMOVE):
  • Sports drinks / Electrolyte drinks with vitamins/minerals (Gatorade, Sqwincher, Pedialyte)
  • Protein shakes and meal replacement drinks
  • Vitamin/mineral beverages (liquid supplements)
  • Hydration formulas with electrolytes
  • Energy drinks with vitamins/supplements

❌ These are NOT supplements (mark as REMOVE):
  • Regular food items (except bars/shakes designed as supplements)
  • Personal care products (lotions, shampoos, soaps)
  • Books, DVDs, equipment
  • Apparel and jewelry
  • Non-nutritional beverages (regular soda, plain juice)

IF NON-SUPPLEMENT DETECTED (and no exceptions apply):
Return JSON with ALL values set to "REMOVE":
{{
  "age": {{"value": "REMOVE", "reasoning": "Non-supplement detected: [reason]"}},
  "gender": {{"value": "REMOVE", "reasoning": "Non-supplement detected: [reason]"}},
  "form": {{"value": "REMOVE", "reasoning": "Non-supplement detected: [reason]"}},
  "organic": {{"value": "REMOVE", "reasoning": "Non-supplement detected: [reason]"}}
}}

This is a SAFETY NET in case non-supplements slip through Step 1 filtering.

================================================================================
TASK: EXTRACT SUPPLEMENT ATTRIBUTES
================================================================================

You will extract 7 attributes from the product title. For EACH attribute, you must:
1. Search for matching keywords
2. Apply any priority rules if needed
3. Provide your reasoning
4. Output the final value

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  CRITICAL: AVOID FALSE POSITIVES FROM BRAND/INGREDIENT NAMES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IGNORE keywords that appear in:
  • Brand names (e.g., "Women's Best" is a brand, NOT a gender indicator)
  • Ingredient names (e.g., "Elderberry" contains "elder", NOT an age indicator)
  
Only EXTRACT keywords that describe:
  • Target audience (age/gender) as a DESCRIPTOR
  • Physical delivery form (not ingredient state)
  • Organic certification

Examples:
  ✅ CORRECT: "Women's Daily Multivitamin" → "Women's" = gender descriptor
  ✅ CORRECT: "Kids Chewable" → "Kids" = age descriptor
  ✅ CORRECT: "Turmeric Powder in Capsules" → Form = "Capsules" (NOT powder)
  ❌ WRONG: "Elderberry Extract" → Do NOT extract "elder" as age
  ❌ WRONG: Brand="Baby's Only" → Do NOT extract "baby" from brand

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

Count Indicators (look for numbers BEFORE these keywords):
"""
    
    for keyword in count_rules['keywords']['count_indicators']:
        prompt += f"  - {keyword}\n"
    
    prompt += "\nVolume Indicators:\n"
    for keyword in count_rules['keywords']['volume_indicators']:
        prompt += f"  - {keyword}\n"
    
    prompt += "\nWeight Indicators (for products like protein powder, creatine):\n"
    for keyword in count_rules['keywords']['weight_indicators']:
        prompt += f"  - {keyword}\n"
    
    prompt += f"\nDefault: {count_rules['default']}\n\n"
    
    # Add examples from JSON
    prompt += "Examples:\n"
    for example in count_rules['examples']:
        prompt += f"  • \"{example['title']}\" → {example['count']}\n"
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

Pack Indicators (keywords that indicate pack size):
"""
    
    for keyword in size_rules['keywords']['pack_indicators']:
        prompt += f"  - {keyword}\n"
    
    prompt += f"\nDefault: {size_rules['default']} ({size_rules['default_reasoning']})\n\n"
    
    # Add examples from JSON
    prompt += "Examples:\n"
    for example in size_rules['examples']:
        prompt += f"  • \"{example['title']}\" → {example['size']}\n"
        prompt += f"    ({example['reasoning']})\n"
    prompt += "\n"
    
    prompt += "⚠️  CRITICAL WARNINGS:\n"
    for warning in size_rules['warnings']:
        prompt += f"  {warning}\n"
    
    # Potency Extraction
    prompt += f"""

================================================================================
STEP 8: EXTRACT POTENCY (DOSAGE/STRENGTH)
================================================================================

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
    
    # Functional Ingredient Extraction
    prompt += f"""

================================================================================
STEP 9: EXTRACT FUNCTIONAL INGREDIENTS
================================================================================

🔍 CRITICAL: This is the MOST IMPORTANT step for determining Category/Subcategory!

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
    
    prompt += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXTRACTION PROCESS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Scan the entire title for ingredient names
2. For EACH ingredient found, record:
   - ingredient_name: The name (e.g., "vitamin d3", "turmeric", "whey protein")
   - position: Character position where it starts in title (0-indexed)
3. For EACH ingredient, call lookup_ingredient() tool to get category/subcategory
4. Return ALL ingredients with their tool results

PRIMARY INGREDIENT DETERMINATION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULE: PRIMARY ingredient = FIRST ingredient by position in title

EXCEPTION: If "multivitamin" or "multiple vitamin" is detected ANYWHERE,
          it becomes PRIMARY regardless of position.

Examples:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Example 1:
Title: "Vitamin D3 with Calcium and Magnesium 120 Softgels"
→ Extract "vitamin d3" at position 0 (PRIMARY ✓) [NOT "vitamin d" + "d3" separately!]
→ Extract "calcium" at position 18
→ Extract "magnesium" at position 30

Example 2:
Title: "Vitamin B12 Methylcobalamin 1000mcg"
→ Extract "vitamin b12" at position 0 (PRIMARY ✓) [NOT "vitamin b" + "b12" separately!]

Example 3:
Title: "Omega-3 Fish Oil 1200mg"
→ Extract "omega-3" at position 0 (PRIMARY ✓) [NOT "omega" + "3" separately!]

PRIMARY INGREDIENT KEYWORDS:
• Multivitamin: {', '.join(ingredient_rules['special_cases']['multivitamin']['keywords'])}
• Protein: {', '.join(ingredient_rules['special_cases']['protein']['keywords'])}

TOOL CALLING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For EACH ingredient found, you MUST call:

  lookup_ingredient(ingredient_name="[ingredient name]")

⚠️  CRITICAL - lookup_ingredient() takes ONLY ingredient_name parameter!

✅ CORRECT EXAMPLES:
  lookup_ingredient(ingredient_name="vitamin d3")
  lookup_ingredient(ingredient_name="calcium")
  lookup_ingredient(ingredient_name="probiotic")

❌ WRONG - DO NOT DO THIS:
  lookup_ingredient(ingredient_name="vitamin d3", position=0)  # ❌ WRONG!
  lookup_ingredient(name="vitamin d3", position=0)  # ❌ WRONG!
  lookup_ingredient("vitamin d3", 0)  # ❌ WRONG!

You track position internally and include it in your FINAL JSON output,
but DO NOT pass position to lookup_ingredient()!

The tool will return:
- ingredient: Normalized name (e.g., "VITAMIN C (NOT ESTER-C)", "PROBIOTIC SUPPLEMENT")
- nw_category: Nature's Way category
- nw_subcategory: Nature's Way subcategory  
- found: Boolean

SPECIAL HANDLING FOR PROBIOTICS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If you extract a specific probiotic strain (akkermansia, lactobacillus, bifidobacterium, etc.)
and lookup_ingredient() returns "found": false,
BUT the title contains "probiotic" or "probiotics":
→ Use lookup_ingredient(ingredient_name="probiotic") instead to get "PROBIOTIC SUPPLEMENT"

Example:
  Title: "Akkermansia Probiotic 300 Billion"
  Step 1: lookup_ingredient(ingredient_name="akkermansia") → returns found: false
  Step 2: Title has "probiotic", so lookup_ingredient(ingredient_name="probiotic") → returns "PROBIOTIC SUPPLEMENT" ✅

SPECIAL HANDLING FOR COMBO PRODUCTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If you see multiple ingredients next to each other (e.g., "echinacea goldenseal"),
try looking up the FULL PHRASE first before splitting:

Example:
  Title: "Echinacea Goldenseal Supreme"
  ✅ CORRECT: lookup_ingredient(ingredient_name="echinacea goldenseal") first
     → If found, use that result ("ECHINACEA GOLDENSEAL COMBO")
     → If not found, then split and look up separately
  
  ❌ WRONG: Immediately split and look up "echinacea" and "goldenseal" separately

⚠️  CRITICAL: USE THE NORMALIZED NAME FROM LOOKUP RESULTS!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When you call lookup_ingredient("vitamin c"), it returns:
  {{"ingredient": "VITAMIN C (NOT ESTER-C)", "nw_category": "...", ...}}

You MUST use the "ingredient" field value in your JSON output:

❌ WRONG:
  {{
    "name": "vitamin c",  ← This is your raw extraction, DON'T use it!
    ...
  }}

✅ CORRECT:
  {{
    "name": "VITAMIN C (NOT ESTER-C)",  ← Use the "ingredient" field from lookup!
    ...
  }}

OUTPUT FORMAT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Include "ingredients" in your final JSON output:

{{
  "ingredients": [
    {{
      "name": "VITAMIN D",
      "position": 0,
      "category": "BASIC VITAMINS & MINERALS",
      "subcategory": "LETTER VITAMINS"
    }},
    {{
      "name": "CALCIUM",
      "position": 18,
      "category": "BASIC VITAMINS & MINERALS",
      "subcategory": "MINERALS"
    }}
  ],
  "primary_ingredient": "VITAMIN D"
}}

⚠️  CRITICAL: You MUST set "primary_ingredient" to the NORMALIZED NAME!
- Use the "ingredient" field from lookup results (e.g., "VITAMIN D", not "vitamin d3")
- If multivitamin is present → "primary_ingredient": "MULTIPLE VITAMIN"
- Otherwise → "primary_ingredient": "[first ingredient by position, NORMALIZED]"
- NEVER use your raw extraction - ALWAYS use the normalized name from lookup!
- NEVER leave it as "N/A" or empty!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

================================================================================
STEP 9: APPLY BUSINESS RULES
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
    
    prompt += """
================================================================================
OUTPUT FORMAT
================================================================================

Return a JSON object with ALL attributes AND business rules result.

EXAMPLE COMPLETE OUTPUT STRUCTURE:

{{
  "age": {{ "value": "AGE GROUP - MATURE ADULT", "reasoning": "..." }},
  "gender": {{ "value": "GENDER - FEMALE", "reasoning": "..." }},
  "form": {{ "value": "SOFTGEL", "reasoning": "..." }},
  "organic": {{ "value": "N/A", "reasoning": "..." }},
  "count": {{ "value": "60", "reasoning": "..." }},
  "unit": {{ "value": "N/A", "reasoning": "..." }},
  "size": {{ "value": "1", "reasoning": "..." }},
  "potency": {{ "value": "5000 IU", "reasoning": "..." }},
  "ingredients": [ /* array from lookup_ingredient calls */ ],
  "primary_ingredient": "multivitamin",
  "business_rules": {{
    "initial_category": "COMBINED MULTIVITAMINS",
    "initial_subcategory": "COMBINED MULTIVITAMINS",
    "final_category": "COMBINED MULTIVITAMINS",
    "final_subcategory": "WOMEN 50+",
    "primary_ingredient": "multivitamin",
    "has_changes": true,
    "has_unknown": false,
    "reasoning": "Refined subcategory from COMBINED MULTIVITAMINS to WOMEN 50+ based on age (MATURE ADULT) and gender (FEMALE)"
  }}
}}

IMPORTANT:
- Always provide reasoning for EVERY attribute extraction
- For count: Be careful NOT to confuse dosage (mg, IU) with count
- For size: Default to 1 if no pack keywords found
- For ingredients: Call lookup_ingredient() for EACH ingredient found
- For business_rules: Call apply_business_rules() AFTER extracting all ingredients
- CRITICAL: Include the full result from apply_business_rules() in your final JSON output
- Provide business_rules.reasoning only when business rules made significant changes

================================================================================
PRODUCT TO CLASSIFY
================================================================================

IMPORTANT: The title may have formatting issues:
- No spaces between words (e.g., "PrenatalMultivitamin")
- All caps or inconsistent capitalization
- Special characters or typos
- Missing punctuation

Your task is to extract information accurately DESPITE these formatting issues.
Interpret the title as best as you can and extract all relevant attributes.

"""
    prompt += f'Title: "{product_title}"\n\n'
    
    prompt += """Now extract all attributes (age, gender, form, organic, count, unit, size, potency, ingredients).

WORKFLOW (CRITICAL - FOLLOW EXACTLY):
1. Extract age, gender, form, organic, count, unit, size, potency from the title
2. Extract ingredient names from the title
3. For EACH ingredient, call lookup_ingredient() to get category/subcategory
4. ⚠️  AFTER ALL lookups are complete, you MUST call apply_business_rules()
   with the ingredients array, age_group, gender, and title

Handle any formatting issues in the title gracefully.

REMINDER: Your final JSON output MUST include the business_rules object!
"""
    
    return prompt


if __name__ == '__main__':
    # Test with example product
    example_title = "Women's 50+ Multivitamin with Turmeric Powder in Vegetable Capsules"
    
    print(build_complete_prompt(example_title))
    
    print("\n" + "="*80)
    print("PROMPT LENGTH:", len(build_complete_prompt(example_title)), "characters")

