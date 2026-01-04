"""
LLM Tools Module

This module contains all custom tools that the LLM can call via function calling.
"""

from .ingredient_lookup import lookup_ingredient, TOOL_DEFINITION as INGREDIENT_TOOL
from .health_focus_lookup import lookup_health_focus  # Used by Python post-processing, not LLM

# Export all tools
__all__ = [
    'lookup_ingredient',
    'INGREDIENT_TOOL',
    'lookup_health_focus',  # Exported for Python use, not as an LLM tool
]

# List of all tool definitions for OpenAI API
ALL_TOOLS = [
    INGREDIENT_TOOL,
    # Note: lookup_health_focus is NOT an LLM tool - it's called from Python post-processing
]

