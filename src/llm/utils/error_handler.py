"""
Error Handler - Centralized retry logic for API calls
"""

import time
import openai
from typing import Callable, Any, Dict
from src.core.log_manager import LogManager


class APIErrorHandler:
    """Handle API errors with retry logic"""
    
    def __init__(self, log_manager: LogManager, asin: str, max_retries: int = 3):
        self.log_manager = log_manager
        self.asin = asin
        self.max_retries = max_retries
    
    def execute_with_retry(self, api_call: Callable, product_id: int) -> Dict[str, Any]:
        """
        Execute API call with retry logic for transient errors
        
        Args:
            api_call: Function to execute (should return dict)
            product_id: Product ID for logging
        
        Returns:
            Result dict with 'success' flag and data or error message
        """
        
        for attempt in range(self.max_retries):
            try:
                # Execute the API call
                result = api_call()
                return {'success': True, 'data': result}
                
            except openai.RateLimitError as rate_error:
                # ✅ TRANSIENT - Retry with exponential backoff
                self.log_manager.log_step(
                    'step2_llm',
                    f"[{self.asin}] Rate limit hit (attempt {attempt + 1}/{self.max_retries})"
                )
                
                if attempt < self.max_retries - 1:
                    wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                    self.log_manager.log_step(
                        'step2_llm',
                        f"[{self.asin}] Waiting {wait_time}s before retry..."
                    )
                    print(f"\n⚠️  Rate limit hit for product {product_id}, waiting {wait_time}s... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    # Max retries reached
                    error_msg = f'Rate limit exceeded after {self.max_retries} retries: {str(rate_error)}'
                    self.log_manager.log_step(
                        'step2_llm',
                        f"[{self.asin}] ERROR: {error_msg}"
                    )
                    return {'success': False, 'error': error_msg}
            
            except (openai.APIConnectionError, openai.APITimeoutError) as conn_error:
                # ⚠️  TRANSIENT - Retry with exponential backoff
                self.log_manager.log_step(
                    'step2_llm',
                    f"[{self.asin}] Connection error (attempt {attempt + 1}/{self.max_retries}): {str(conn_error)[:100]}"
                )
                
                if attempt < self.max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    self.log_manager.log_step(
                        'step2_llm',
                        f"[{self.asin}] Retrying in {wait_time}s..."
                    )
                    print(f"\n⚠️  Connection error for product {product_id}, retrying... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    error_msg = f'Connection failed after {self.max_retries} retries: {str(conn_error)}'
                    self.log_manager.log_step(
                        'step2_llm',
                        f"[{self.asin}] ERROR: {error_msg}"
                    )
                    return {'success': False, 'error': error_msg}
            
            except (openai.AuthenticationError, openai.PermissionDeniedError) as auth_error:
                # ❌ AUTH ERRORS - Fail immediately (no retry)
                error_msg = f'Authentication error: {str(auth_error)}'
                self.log_manager.log_step(
                    'step2_llm',
                    f"[{self.asin}] ERROR: {error_msg}"
                )
                return {'success': False, 'error': error_msg}
            
            except Exception as api_error:
                error_str = str(api_error)
                error_type = type(api_error).__name__
                
                # Check if it's a tool call error (LLM formatting issue) - these are retryable
                is_tool_call_error = (
                    'unexpected keyword argument' in error_str or
                    'Invalid JSON' in error_str or
                    'lookup_ingredient()' in error_str or
                    'apply_business_rules()' in error_str or
                    'got an unexpected keyword' in error_str
                )
                
                if is_tool_call_error and attempt < self.max_retries - 1:
                    # ⚠️  TRANSIENT - Tool call formatting error, retry
                    self.log_manager.log_step(
                        'step2_llm',
                        f"[{self.asin}] Tool call error (attempt {attempt + 1}/{self.max_retries}): {error_str[:150]}"
                    )
                    wait_time = 2  # Short wait for tool call errors
                    print(f"\n⚠️  Tool call error for product {product_id}, retrying... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                    continue
                
                # ❌ OTHER ERRORS - Fail immediately
                error_msg = f'{error_type}: {error_str}'
                self.log_manager.log_step(
                    'step2_llm',
                    f"[{self.asin}] ERROR: {error_msg[:200]}"
                )
                return {'success': False, 'error': error_msg}
        
        # Should never reach here
        return {'success': False, 'error': 'Max retries exceeded'}

