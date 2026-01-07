"""
Step 2: LLM Extraction - Extract product attributes using GPT
"""

from typing import Dict, Any
from src.llm.gpt_client import GPTClient
from src.llm.prompt_builder import build_complete_prompt
from src.llm.tools import ALL_TOOLS
from src.llm.tools.ingredient_lookup import lookup_ingredient
from src.llm.tools.business_rules_tool import apply_business_rules_tool
from src.core.log_manager import LogManager
from src.llm.utils.error_handler import APIErrorHandler


def extract_llm_attributes(
    title: str,
    asin: str,
    product_id: int,
    log_manager: LogManager,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Extract product attributes using LLM with tool calling
    
    Args:
        title: Product title
        asin: Product ASIN
        product_id: Product ID for logging
        log_manager: Log manager instance
        max_retries: Max retry attempts for transient errors
    
    Returns:
        Dict with 'success' flag and either 'data' or 'error'
        data contains: llm_result with extracted attributes + metadata
    """
    
    log_manager.log_step('step2_llm', f"[{asin}] Starting LLM extraction: {title[:60]}...")
    
    # Initialize error handler
    error_handler = APIErrorHandler(log_manager, asin, max_retries)
    
    # Define the API call function
    def make_llm_call():
        client = GPTClient()
        client.register_tool('lookup_ingredient', lookup_ingredient)
        client.register_tool('apply_business_rules', apply_business_rules_tool)
        
        prompt = build_complete_prompt(title)
        # IMPORTANT: use_schema=False because business_rules is populated via tool call
        # The schema is too strict and doesn't allow for the tool call workflow
        return client.extract_attributes(prompt, tools=ALL_TOOLS, use_schema=False)
    
    # Execute with retry logic
    result = error_handler.execute_with_retry(make_llm_call, product_id)
    
    # Check result
    if not result['success']:
        return result
    
    llm_result = result['data']
    
    # Check if LLM returned error
    if 'error' in llm_result:
        error_msg = llm_result.get('error', 'Unknown error')
        log_manager.log_step('step2_llm', f"[{asin}] ERROR in LLM result: {error_msg}")
        return {'success': False, 'error': error_msg}
    
    # Log success
    metadata = llm_result.get('_metadata', {})
    tokens = metadata.get('tokens_used', {})  # ✅ FIXED: was 'tokens', should be 'tokens_used'
    total_tokens = tokens.get('total', 0)
    prompt_tokens = tokens.get('prompt', 0)
    completion_tokens = tokens.get('completion', 0)
    cost = metadata.get('total_cost', 0)
    
    log_manager.log_step(
        'step2_llm',
        f"[{asin}] SUCCESS - Tokens: {total_tokens:,} (in: {prompt_tokens:,}, out: {completion_tokens:,}), Cost: ${cost:.4f}"
    )
    
    # Log extracted ingredients
    ingredients = llm_result.get('ingredients', [])
    log_manager.log_step('step2_llm', f"[{asin}] Extracted {len(ingredients)} ingredients")
    
    return {'success': True, 'data': llm_result}


def extract_attributes_from_llm_result(llm_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract individual attributes from LLM result (DRY helper)
    
    Args:
        llm_result: Raw LLM response
    
    Returns:
        Dict with extracted attributes
    """
    # Handle ingredients - may be direct array OR wrapped in {value: [...], reasoning: "..."}
    ingredients_raw = llm_result.get('ingredients', [])
    if isinstance(ingredients_raw, dict) and 'value' in ingredients_raw:
        ingredients = ingredients_raw['value']  # Unwrap if LLM wrapped it
    else:
        ingredients = ingredients_raw  # Use as-is if it's already an array
    
    # Normalize ingredient structure - flatten lookup_result if present
    normalized_ingredients = []
    for ing in ingredients:
        if isinstance(ing, dict):
            # If LLM nested category/subcategory in lookup_result, flatten it
            if 'lookup_result' in ing:
                lookup = ing['lookup_result']
                ing_normalized = ing.copy()
                # Move nw_category/nw_subcategory to top level as category/subcategory
                ing_normalized['category'] = lookup.get('nw_category')
                ing_normalized['subcategory'] = lookup.get('nw_subcategory')
                ing_normalized['found'] = lookup.get('found', False)
                normalized_ingredients.append(ing_normalized)
            else:
                # Already in correct format or missing fields
                normalized_ingredients.append(ing)
        else:
            # String ingredient
            normalized_ingredients.append({'name': str(ing), 'position': 999})
    
    return {
        'age': llm_result.get('age', {}).get('value', 'N/A'),
        'gender': llm_result.get('gender', {}).get('value', 'N/A'),
        'form': llm_result.get('form', {}).get('value', 'N/A'),
        'organic': llm_result.get('organic', {}).get('value', 'N/A'),
        'count': llm_result.get('count', {}).get('value', 'N/A'),
        'unit': llm_result.get('unit', {}).get('value', 'N/A'),
        'size': llm_result.get('size', {}).get('value', 'N/A'),
        'potency': llm_result.get('potency', {}).get('value', ''),
        'ingredients': normalized_ingredients,
        'business_rules': llm_result.get('business_rules', {})
    }


def extract_metadata_from_llm_result(llm_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract token usage and cost metadata from LLM result (DRY helper)
    
    Args:
        llm_result: Raw LLM response
    
    Returns:
        Dict with metadata (tokens_used, cost, tokens_breakdown, full_metadata)
    """
    metadata = llm_result.get('_metadata', {})
    tokens = metadata.get('tokens_used', {})  # ✅ FIXED: was 'tokens', should be 'tokens_used'
    
    return {
        'tokens_used': tokens.get('total', 0),
        'api_cost': metadata.get('total_cost', 0),
        'tokens_breakdown': tokens,
        '_metadata': metadata
    }

