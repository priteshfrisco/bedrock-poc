"""
Weight Unit Converter - Post-Processing for Count/Unit

This module handles weight unit conversions (lb, kg, g, mg, ml → OZ)
after LLM extraction. Matches R system's conversion logic exactly.
"""

import json
from pathlib import Path


# Conversion factors (matching R system exactly)
WEIGHT_TO_OZ = {
    'lb': 16.0,
    'kg': 35.274,
    'g': 0.035274,
    'mg': 0.000035274,
    'ml': 0.033814
}


def load_conversion_factors():
    """
    Load conversion factors from unit_extraction_rules.json
    (backup in case we want to make factors configurable)
    """
    try:
        rules_path = Path(__file__).parent.parent.parent / 'reference_data' / 'unit_extraction_rules.json'
        with open(rules_path, 'r', encoding='utf-8') as f:
            rules = json.load(f)
            return rules.get('conversion_factors_for_python', WEIGHT_TO_OZ)
    except Exception:
        # Fallback to hardcoded values if file not found
        return WEIGHT_TO_OZ


def convert_weight_to_oz(count, unit):
    """
    Convert weight units to OZ using R system's conversion factors.
    
    Args:
        count: Numeric count value (string or float/int)
        unit: Unit string ('lb', 'kg', 'g', 'mg', 'ml', 'oz', 'COUNT', etc.)
        
    Returns:
        tuple: (converted_count, converted_unit, conversion_info)
        
    Examples:
        >>> convert_weight_to_oz("2", "lb")
        (32.0, "OZ", "Converted 2 lb to 32.0 oz (2 × 16.0)")
        
        >>> convert_weight_to_oz("500", "g")
        (17.637, "OZ", "Converted 500 g to 17.637 oz (500 × 0.035274)")
        
        >>> convert_weight_to_oz("180", "COUNT")
        (180, "COUNT", "No conversion (discrete units)")
    """
    # Handle UNKNOWN or missing values
    if count == "UNKNOWN" or unit == "UNKNOWN" or not count or not unit:
        return count, unit, "No conversion (UNKNOWN values)"
    
    # Handle COUNT (discrete units) - no conversion
    if unit == "COUNT":
        return count, unit, "No conversion (discrete units)"
    
    # Handle oz/OZ - already in desired format
    if unit.lower() in ['oz', 'ounce', 'ounces', 'fl oz', 'fluid oz']:
        return count, "OZ", "No conversion (already in OZ)"
    
    # Convert weight units to OZ
    unit_lower = unit.lower()
    
    conversion_factors = load_conversion_factors()
    
    if unit_lower in conversion_factors:
        try:
            # Convert count to float for calculation
            count_numeric = float(count)
            
            # Get conversion factor
            factor = conversion_factors[unit_lower]
            
            # Perform conversion
            converted_count = count_numeric * factor
            
            # Round to match R's precision (keep up to 6 decimal places)
            converted_count = round(converted_count, 6)
            
            # Build conversion info string
            conversion_info = f"Converted {count} {unit} to {converted_count} oz ({count} × {factor})"
            
            return converted_count, "OZ", conversion_info
            
        except (ValueError, TypeError) as e:
            # If conversion fails, return original values
            return count, unit, f"Conversion failed: {str(e)}"
    
    # If unit not recognized as weight unit, return as-is
    return count, unit, f"No conversion (unit '{unit}' not a weight unit)"


def process_product_attributes(attributes):
    """
    Process LLM-extracted attributes and apply weight conversions.
    
    Args:
        attributes: Dict with 'count' and 'unit' keys (from LLM output)
        
    Returns:
        dict: Updated attributes with converted count/unit and reasoning
        
    Example:
        >>> attrs = {
        ...     "count": {"value": "2", "reasoning": "Found '2 lbs'"},
        ...     "unit": {"value": "lb", "reasoning": "Weight unit 'lbs' found"}
        ... }
        >>> process_product_attributes(attrs)
        {
            "count": {"value": 32.0, "reasoning": "Found '2 lbs' → Converted to 32.0 oz"},
            "unit": {"value": "OZ", "reasoning": "Weight unit 'lbs' found → Converted to OZ"}
        }
    """
    # Extract count and unit values
    count_value = attributes.get('count', {}).get('value', 'UNKNOWN')
    count_reasoning = attributes.get('count', {}).get('reasoning', '')
    
    unit_value = attributes.get('unit', {}).get('value', 'UNKNOWN')
    unit_reasoning = attributes.get('unit', {}).get('reasoning', '')
    
    # Perform conversion
    converted_count, converted_unit, conversion_info = convert_weight_to_oz(count_value, unit_value)
    
    # Update attributes with converted values
    if converted_count != count_value or converted_unit != unit_value:
        # Conversion happened - update reasoning
        attributes['count']['value'] = converted_count
        attributes['count']['reasoning'] = f"{count_reasoning} → {conversion_info}"
        
        attributes['unit']['value'] = converted_unit
        attributes['unit']['reasoning'] = f"{unit_reasoning} → {conversion_info}"
    
    return attributes


# Example usage
if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("2", "lb"),
        ("500", "g"),
        ("1", "kg"),
        ("180", "COUNT"),
        ("8", "oz"),
        ("UNKNOWN", "UNKNOWN")
    ]
    
    print("Testing Weight Unit Converter")
    print("=" * 80)
    
    for count, unit in test_cases:
        converted_count, converted_unit, info = convert_weight_to_oz(count, unit)
        print(f"\nInput:  count={count}, unit={unit}")
        print(f"Output: count={converted_count}, unit={converted_unit}")
        print(f"Info:   {info}")

