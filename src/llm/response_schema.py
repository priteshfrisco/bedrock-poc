"""
JSON Schema for GPT-5-mini Structured Outputs
Defines the exact structure of the LLM response
"""

# Define the response schema for structured outputs
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "age": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "reasoning": {"type": "string"}
            },
            "required": ["value", "reasoning"],
            "additionalProperties": False
        },
        "gender": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "reasoning": {"type": "string"}
            },
            "required": ["value", "reasoning"],
            "additionalProperties": False
        },
        "form": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "reasoning": {"type": "string"}
            },
            "required": ["value", "reasoning"],
            "additionalProperties": False
        },
        "organic": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "reasoning": {"type": "string"}
            },
            "required": ["value", "reasoning"],
            "additionalProperties": False
        },
        "count": {
            "type": "object",
            "properties": {
                "value": {"type": ["string", "number"]},  # Can be string or number
                "reasoning": {"type": "string"}
            },
            "required": ["value", "reasoning"],
            "additionalProperties": False
        },
        "unit": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "reasoning": {"type": "string"}
            },
            "required": ["value", "reasoning"],
            "additionalProperties": False
        },
        "size": {
            "type": "object",
            "properties": {
                "value": {"type": ["integer", "number"]},
                "reasoning": {"type": "string"}
            },
            "required": ["value", "reasoning"],
            "additionalProperties": False
        },
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "position": {"type": "integer"},
                    "category": {"type": ["string", "null"]},
                    "subcategory": {"type": ["string", "null"]}
                },
                "required": ["name", "position"],
                "additionalProperties": False
            }
        },
        "primary_ingredient": {
            "type": ["string", "null"],
            "description": "Name of the primary ingredient (first by position or multivitamin)"
        },
        "business_rules": {
            "type": "object",
            "properties": {
                "initial_category": {"type": "string"},
                "initial_subcategory": {"type": "string"},
                "final_category": {"type": "string"},
                "final_subcategory": {"type": "string"},
                "primary_ingredient": {"type": "string"},
                "has_changes": {"type": "boolean"},
                "has_unknown": {"type": "boolean"},
                "reasoning": {
                    "type": ["string", "null"],
                    "description": "Reasoning explaining changes - only if should_explain was true"
                }
            },
            "required": ["final_category", "final_subcategory", "primary_ingredient"],
            "additionalProperties": False
        }
    },
    "required": ["age", "gender", "form", "organic", "count", "unit", "size", "ingredients", "primary_ingredient", "business_rules"],
    "additionalProperties": False
}


# Simpler schema format for response_format parameter
RESPONSE_FORMAT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "supplement_attributes",
        "strict": True,
        "schema": RESPONSE_SCHEMA
    }
}


if __name__ == '__main__':
    import json
    print("="*80)
    print("RESPONSE SCHEMA FOR STRUCTURED OUTPUTS:")
    print("="*80)
    print(json.dumps(RESPONSE_SCHEMA, indent=2))
    print("\n" + "="*80)
    print("✅ Schema defines:")
    print("  - All required fields (age, gender, form, organic, count, unit, size, ingredients)")
    print("  - Each attribute has: value + reasoning")
    print("  - Ingredients array with: name, position, category, subcategory")
    print("  - primary_ingredient field")
    print("  - strict=True enforces exact schema (no extra fields)")
    print("="*80)
