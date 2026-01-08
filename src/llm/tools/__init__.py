"""
LLM Tools Module

This module contains all custom tools that the LLM can call via function calling.
"""

from .ingredient_lookup import lookup_ingredient, TOOL_DEFINITION as INGREDIENT_TOOL
from .health_focus_lookup import lookup_health_focus  # Used by postprocessing tool internally
from .business_rules_tool import apply_business_rules_tool, TOOL_DEFINITION as BUSINESS_RULES_TOOL
from .postprocessing_tool import apply_postprocessing_tool, TOOL_DEFINITION as POSTPROCESSING_TOOL

# Export all tools
__all__ = [
    'lookup_ingredient',
    'apply_business_rules_tool',
    'apply_postprocessing_tool',
    'INGREDIENT_TOOL',
    'BUSINESS_RULES_TOOL',
    'POSTPROCESSING_TOOL',
    'lookup_health_focus',  # Exported for internal use by postprocessing tool
]

# List of all tool definitions for OpenAI API
ALL_TOOLS = [
    INGREDIENT_TOOL,
    BUSINESS_RULES_TOOL,
    POSTPROCESSING_TOOL,  # LLM calls this for final processing
]


