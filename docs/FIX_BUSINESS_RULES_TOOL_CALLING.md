# Fix: Business Rules Tool Calling

## Issue
The LLM was not calling the `apply_business_rules` tool after extracting ingredients, even though:
- The tool was properly registered
- The prompt explicitly instructed the LLM to call it
- GPT-5-mini supports multiple rounds of tool calling

## Root Cause
In `src/llm/gpt_client.py`, after the first round of tool calls (e.g., `lookup_ingredient`), the code was sending tool results back to the LLM for a final response, **but it wasn't including the `tools` parameter** in the API call (lines 117-125).

This meant:
1. LLM would call `lookup_ingredient` for each ingredient (first round) ✅
2. Tool results were sent back to LLM
3. LLM wanted to call `apply_business_rules` (second round) ❌
4. But since `tools` wasn't included, the LLM couldn't make another tool call
5. Instead, it returned JSON describing the tool call it wanted to make

## Solution
Updated `src/llm/gpt_client.py` to include `tools` and `tool_choice` parameters when sending tool results back to the LLM:

```python
# Send tool results back to LLM for final response
# IMPORTANT: Include tools again so LLM can make more tool calls if needed
final_response_format = RESPONSE_FORMAT_SCHEMA if use_schema else {"type": "json_object"}
final_params = {
    "model": self.model,
    "messages": messages,
    "response_format": final_response_format
}
if tools:
    final_params["tools"] = tools
    final_params["tool_choice"] = "auto"  # Let LLM decide if it needs more tool calls

response = self.client.chat.completions.create(**final_params)
```

## Results
After the fix:
- ✅ LLM now calls `apply_business_rules` after all `lookup_ingredient` calls
- ✅ Business rules reasoning is generated for significant changes
- ✅ UNKNOWN ingredients get explanatory reasoning
- ✅ Reasoning only appears when needed (not for every product)

## Test Results (sample_10_test.csv)
- Total products: 10
- Supplements processed: 4
- Products with reasoning: 2

### Examples:

**1. Multivitamin with subcategory refinement:**
- Category: COMBINED MULTIVITAMINS / NON-SPECIFIC
- Reasoning: "Primary ingredient set to 'multivitamin'; initial category COMBINED MULTIVITAMINS was refined to subcategory NON-SPECIFIC because both extracted age and gender are NON SPECIFIC."

**2. Unknown ingredient:**
- Category: UNKNOWN / UNKNOWN  
- Reasoning: "Primary ingredient determined as 'presgera' (first ingredient by position). 'presgera' was not found in the ingredient database, so category/subcategory remain UNKNOWN."

## Date
2026-01-04

