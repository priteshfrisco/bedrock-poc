# COMPLETE REASONING COLLECTION MAP

## Overview
This document maps **ALL places** where reasoning is collected throughout the pipeline.

---

## STEP 1: NON-SUPPLEMENT FILTERING

### Location: `src/pipeline/step1_filter.py`

### Reasoning Collected:

#### 1.1 **Filter Reason** (for filtered-out records)
- **Type**: String explanation
- **When**: Product fails Step 1 filtering
- **Examples**:
  - `"Books and media products are non-supplements"`
  - `"Contains non-supplement keyword: 'shampoo'"`
  - `"Amazon subcategory not found in lookup table"`
- **Stored in**: `result['filter_reason']`
- **Detail Level**: Medium (1 sentence)

#### 1.2 **Filter Type** (categorical)
- **Type**: Enum
- **Values**: 
  - `'filtered_by_remove'` - Amazon subcategory marked as REMOVE
  - `'filtered_by_keyword'` - Title contains non-supplement keywords
- **Stored in**: `result['filter_type']`

#### 1.3 **Remap Reason** (for REMAP actions)
- **Type**: String explanation
- **When**: Amazon subcategory maps to NW category/subcategory
- **Examples**:
  - `"Maps to BASIC VITAMINS & MINERALS / MINERALS"`
  - `"Reclassified from antioxidants to proper category"`
- **Stored in**: `result['remap_reason']`
- **Detail Level**: Short (1 line)

---

## STEP 2: LLM EXTRACTION

### Location: `src/pipeline/step2_llm.py` + `src/llm/gpt_client.py`

### Reasoning Collected:

#### 2.1 **LLM Attribute Reasoning** (for EACH attribute)
- **Type**: JSON object with reasoning field for each attribute
- **Attributes with reasoning**:
  - Age (`age.reasoning`)
  - Gender (`gender.reasoning`)
  - Form (`form.reasoning`)
  - Organic (`organic.reasoning`)
  - Count (`count.reasoning`)
  - Unit (`unit.reasoning`)
  - Size (`size.reasoning`)

**Example LLM Response:**
```json
{
  "age": {
    "value": "AGE GROUP - NON SPECIFIC",
    "reasoning": "No age keywords found in title"
  },
  "gender": {
    "value": "GENDER - NON SPECIFIC",
    "reasoning": "No gender keywords found"
  },
  "form": {
    "value": "SOFTGEL",
    "reasoning": "Title contains 'softgels' keyword"
  },
  "organic": {
    "value": "NOT ORGANIC",
    "reasoning": "No organic keywords found"
  },
  "count": {
    "value": 120,
    "reasoning": "Found '120 softgels' in title"
  },
  "unit": {
    "value": "COUNT",
    "reasoning": "Discrete units (softgels)"
  },
  "size": {
    "value": 1,
    "reasoning": "No pack keywords found, default to 1"
  }
}
```

- **Stored in**: `step2_result['_metadata']['raw_llm_response']`
- **Detail Level**: Medium (1-2 sentences per attribute)
- **Coverage**: 7 attributes per product

#### 2.2 **Tool Call Results** (ingredient lookups)
- **Type**: Array of tool call objects
- **Contains**:
  - Function name: `lookup_ingredient`
  - Arguments: `{ingredient_name: "coq10"}`
  - Result: Full ingredient lookup response (category, subcategory, match_type, confidence, score)

**Example:**
```json
{
  "tool_calls": [
    {
      "function": "lookup_ingredient",
      "arguments": {"ingredient_name": "coq10"},
      "result": {
        "found": true,
        "ingredient": "Co Q10",
        "nw_category": "BASIC VITAMINS & MINERALS",
        "nw_subcategory": "COENZYME Q10",
        "keyword": "coq10",
        "match_type": "exact",
        "confidence": "exact",
        "score": 100
      }
    },
    {
      "function": "lookup_ingredient",
      "arguments": {"ingredient_name": "bioperine"},
      "result": {
        "found": true,
        "ingredient": "Bioperine",
        "nw_category": "FATTY ACIDS",
        "nw_subcategory": "HEMP/CBD",
        "match_type": "exact",
        "confidence": "exact",
        "score": 100
      }
    }
  ]
}
```

- **Stored in**: `result['_metadata']['tool_calls']`
- **Detail Level**: High (complete lookup details)
- **Count**: Variable (1-20 ingredients per product)

#### 2.3 **Unit Conversion Reasoning**
- **Location**: `src/pipeline/utils/unit_converter.py`
- **Type**: String explanation of weight→oz conversions
- **Examples**:
  - `"Found '2 lbs' → Converted to 32.0 oz"`
  - `"No conversion (unit 'COUNT' not a weight unit)"`
- **Stored in**: `attributes['count']['reasoning']` and `attributes['unit']['reasoning']`
- **Detail Level**: Short (1 line)

---

## STEP 3: POST-PROCESSING & BUSINESS RULES

### Location: `src/pipeline/step3_postprocess.py` + `src/pipeline/utils/business_rules.py`

### Reasoning Collected:

#### 3.1 **Business Rules Reasoning** (combined)
- **Type**: Multi-part string with pipe separators
- **Built from 6 sources**:

**Part 1: Primary Ingredient Selection**
```
"Primary Ingredient: 'coq10' (position 0)"
```

**Part 2: Initial Category Assignment**
```
"Initial Category/Subcategory: BASIC VITAMINS & MINERALS / MINERALS"
```

**Part 3: Title-Based Overrides** (if applicable)
```
"Title Override: 'protein powder' → ACTIVE NUTRITION / PERFORMANCE NUTRITION"
```
- **When**: Title contains specific keywords (protein powder, weight loss, etc.)
- **Function**: `apply_title_based_overrides()`

**Part 4: Ingredient-Specific Overrides** (if applicable)
```
"Ingredient Override: SAM-E → HERBAL REMEDIES / SINGLES"
```
or
```
"Ingredient Override: CoQ10 → BASIC VITAMINS & MINERALS / COENZYME Q10"
```
- **When**: Primary ingredient is SAM-E, algae, CoQ10, probiotics
- **Function**: `apply_ingredient_specific_overrides()`

**Part 5: Protein Rule** (if applicable)
```
"Protein Rule: Primary ingredient 'whey' → ACTIVE NUTRITION / PERFORMANCE NUTRITION"
```
- **When**: Primary ingredient contains protein keywords
- **Function**: `apply_protein_rule()`

**Part 6: Herb Formula Rule** (if applicable)
```
"Herb Rule: Found 4 herbs → HERBAL REMEDIES / FORMULAS"
```
or
```
"Herb Rule: Found 1 herb → HERBAL REMEDIES / SINGLES"
```
- **When**: Product contains herbal ingredients
- **Function**: `apply_herb_formula_rule()`

**Part 7: Multivitamin Refinement** (if applicable)
```
"Multivitamin Refinement: Gender=FEMALE + Age=MATURE ADULT → Subcategory=WOMEN MATURE"
```
- **When**: Category is COMBINED MULTIVITAMINS
- **Function**: `apply_multivitamin_refinement()`
- **Uses**: Age + Gender + Title keywords

**Final Combined Format:**
```
"Primary Ingredient: 'coq10' (position 0) | Initial Category/Subcategory: BASIC VITAMINS & MINERALS / MINERALS | Ingredient Override: CoQ10 → BASIC VITAMINS & MINERALS / COENZYME Q10"
```

- **Stored in**: `business_result['reasoning']`
- **Detail Level**: High (complete decision trail)
- **Length**: 100-300 characters

#### 3.2 **Health Focus Lookup Result**
- **Type**: Health focus match details
- **Contains**:
  - `found`: boolean
  - `ingredient`: normalized name
  - `health_focus`: health focus category
  - `match_type`: exact/fuzzy/bm25
  - `confidence`: high/medium/low
  - `score`: numeric score

**Example:**
```json
{
  "found": true,
  "ingredient": "Co Q10",
  "health_focus": "HEART HEALTH",
  "match_type": "exact",
  "confidence": "high",
  "score": 100
}
```

- **Stored in**: Logs only (not in final result)
- **Detail Level**: Medium

---

## REASONING NOT CURRENTLY CAPTURED (but available)

### 1. **Exact LLM Prompt Sent**
- **Location**: `src/llm/prompt_builder.py`
- **Size**: ~18,000 characters per product
- **Contains**: Full instructions, examples, extraction rules
- **Currently**: Not saved (could be saved in audit files)

### 2. **LLM Token Usage**
- **Captured**: Yes
- **Stored in**: `result['tokens_used']` and `result['_metadata']['tokens_used']`
- **Contains**: prompt_tokens, completion_tokens, total

### 3. **Processing Time**
- **Captured**: Yes
- **Stored in**: `result['processing_time_sec']`

### 4. **Retry Attempts** (if LLM fails)
- **Currently**: Logged but not stored in result
- **Could add**: Number of retries, error messages

---

## SUMMARY: REASONING DATA VOLUME

### Per Product Record:

| Source | Type | Size | Always Present? |
|--------|------|------|----------------|
| Step 1: Filter Reason | String | 50-200 chars | Only if filtered |
| Step 1: Remap Reason | String | 30-100 chars | Only if remapped (~10-30%) |
| Step 2: LLM Attribute Reasoning (x7) | JSON | 300-800 chars | Yes |
| Step 2: Tool Call Results | JSON Array | 500-2000 chars | Yes (varies by ingredients) |
| Step 2: Unit Conversion | String | 30-100 chars | Only if converted |
| Step 3: Business Rules Reasoning | String | 100-300 chars | Yes |
| Step 3: Health Focus Lookup | JSON | 100-200 chars | Yes (logged only) |

**Total Reasoning Data Per Record:**
- **Minimum** (standard processing): ~1,000 chars (1 KB)
- **Average** (with overrides): ~2,000 chars (2 KB)
- **Maximum** (complex cases): ~3,500 chars (3.5 KB)

**For 40,000 Records:**
- **Minimum Total**: 40 MB
- **Average Total**: 80 MB
- **Maximum Total**: 140 MB

---

## CURRENT STORAGE STRATEGY

### What's Currently Saved:

1. **Audit JSON Files** (per product):
   - Full reasoning from all steps
   - All tool calls
   - LLM metadata
   - Processing time
   - Location: `data/audit/{file_id}/{run_id}/step[1-3]/{asin}.json`

2. **Final Output CSV**:
   - **NO reasoning columns currently**
   - Only final values (category, subcategory, age, gender, etc.)
   - Location: `data/output/{file_id}/{run_id}/coded_{filename}.csv`

3. **Log Files**:
   - Step-by-step processing logs
   - Location: `data/logs/{file_id}/{run_id}/step[1-3].log`

---

## REASONING TYPES BY IMPORTANCE

### **CRITICAL** (Always want to know):
1. ✅ Business rule overrides (e.g., CoQ10 → COENZYME Q10)
2. ✅ Step 1 Remap (Amazon subcat → NW category)
3. ✅ Multivitamin refinement (age+gender logic)
4. ✅ Herb formula vs singles decision

### **IMPORTANT** (Good to have for exceptions):
5. ⚠️ Step 1 filter reasons (only for filtered records)
6. ⚠️ Tool call results (when ingredient match confidence is low)
7. ⚠️ Unit conversions (when lb→oz conversion happens)

### **NICE TO HAVE** (Debugging):
8. ℹ️ LLM attribute reasoning (usually straightforward)
9. ℹ️ Health focus lookup details
10. ℹ️ Processing time and token usage

---

## NEXT STEPS

Based on this analysis, we need to decide:

1. **Which reasoning to include in output CSV?**
   - All? (too much)
   - Critical only? (smart)
   - Conditional based on flags? (very smart)

2. **What format?**
   - Single reasoning column?
   - Multiple columns (one per type)?
   - Flag codes + optional reasoning?

3. **How to handle 40k+ records?**
   - Keep file size manageable
   - Make it searchable/filterable
   - Balance detail vs usability

