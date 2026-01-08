"""
Weight Unit Converter - Post-Processing for Size/Unit

This module handles weight unit conversions (lb, kg, g, mg, ml → OZ)
after LLM extraction. Matches R system's conversion logic exactly.

Field naming aligns with Master File:
- 'size' = quantity (60, 120, 35.274) → outputs to 'SIZE' column
- 'pack_count' = pack size (1, 2, 3) → outputs to 'Pack Count' column
"""

import json
from pathlib import Path


def load_conversion_factors():
    """
    Load conversion factors from unit_extraction_rules.json
    
    Conversion factors (matching R system exactly):
    - lb → × 16 = OZ
    - kg → × 35.274 = OZ
    - g → × 0.035274 = OZ
    - mg → × 0.000035274 = OZ
    - ml → × 0.033814 = OZ
    
    Raises:
        FileNotFoundError: If unit_extraction_rules.json is not found
        ValueError: If conversion factors are missing from the file
    """
    # Go up from src/pipeline/utils/ to workspace root, then into reference_data/
    rules_path = Path(__file__).parent.parent.parent.parent / 'reference_data' / 'unit_extraction_rules.json'
    
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            rules = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Required file not found: {rules_path}\n"
            "Cannot perform unit conversions without conversion factors."
        )
    
    conversion_factors = rules.get('conversion_factors_for_python')
    if not conversion_factors:
        raise ValueError(
            f"Missing 'conversion_factors_for_python' in {rules_path}\n"
            "Cannot perform unit conversions without conversion factors."
        )
    
    return conversion_factors


def convert_weight_to_oz(size, unit):
    """
    Convert weight units to OZ using R system's conversion factors.
    
    Args:
        size: Numeric size value (string or float/int) - the quantity
        unit: Unit string ('lb', 'kg', 'g', 'mg', 'ml', 'oz', 'COUNT', etc.)
        
    Returns:
        tuple: (converted_size, converted_unit, conversion_info)
        
    Examples:
        >>> convert_weight_to_oz("2", "lb")
        (32.0, "OZ", "Converted 2 lb to 32.0 oz (2 × 16.0)")
        
        >>> convert_weight_to_oz("500", "g")
        (17.637, "OZ", "Converted 500 g to 17.637 oz (500 × 0.035274)")
        
        >>> convert_weight_to_oz("180", "COUNT")
        (180, "COUNT", "No conversion (discrete units)")
    """
    # Handle UNKNOWN or missing values
    if size == "UNKNOWN" or unit == "UNKNOWN" or not size or not unit:
        return size, unit, "No conversion (UNKNOWN values)"
    
    # Handle COUNT (discrete units) - no conversion
    if unit == "COUNT":
        return size, unit, "No conversion (discrete units)"
    
    # Handle oz/OZ - already in desired format
    if unit.lower() in ['oz', 'ounce', 'ounces', 'fl oz', 'fluid oz']:
        return size, "OZ", "No conversion (already in OZ)"
    
    # Convert weight units to OZ
    unit_lower = unit.lower()
    
    conversion_factors = load_conversion_factors()
    
    if unit_lower in conversion_factors:
        try:
            # Convert size to float for calculation
            size_numeric = float(size)
            
            # Get conversion factor
            factor = conversion_factors[unit_lower]
            
            # Perform conversion
            converted_size = size_numeric * factor
            
            # Round to match R's precision (keep up to 6 decimal places)
            converted_size = round(converted_size, 6)
            
            # Build conversion info string
            conversion_info = f"Converted {size} {unit} to {converted_size} oz ({size} × {factor})"
            
            return converted_size, "OZ", conversion_info
            
        except (ValueError, TypeError) as e:
            # If conversion fails, return original values
            return size, unit, f"Conversion failed: {str(e)}"
    
    # If unit not recognized as weight unit, return as-is
    return size, unit, f"No conversion (unit '{unit}' not a weight unit)"


def process_product_attributes(attributes):
    """
    Process LLM-extracted attributes and apply weight conversions.
    
    Args:
        attributes: Dict with 'size' and 'unit' keys (from LLM output)
        
    Returns:
        dict: Updated attributes with converted size/unit and reasoning
        
    Example:
        >>> attrs = {
        ...     "size": {"value": "2", "reasoning": "Found '2 lbs'"},
        ...     "unit": {"value": "lb", "reasoning": "Weight unit 'lbs' found"}
        ... }
        >>> process_product_attributes(attrs)
        {
            "size": {"value": 32.0, "reasoning": "Found '2 lbs' → Converted to 32.0 oz"},
            "unit": {"value": "OZ", "reasoning": "Weight unit 'lbs' found → Converted to OZ"}
        }
    """
    # Extract size and unit values
    size_value = attributes.get('size', {}).get('value', 'UNKNOWN')
    size_reasoning = attributes.get('size', {}).get('reasoning', '')
    
    unit_value = attributes.get('unit', {}).get('value', 'UNKNOWN')
    unit_reasoning = attributes.get('unit', {}).get('reasoning', '')
    
    # Perform conversion
    converted_size, converted_unit, conversion_info = convert_weight_to_oz(size_value, unit_value)
    
    # Update attributes with converted values
    if converted_size != size_value or converted_unit != unit_value:
        # Conversion happened - update reasoning
        attributes['size']['value'] = converted_size
        attributes['size']['reasoning'] = f"{size_reasoning} → {conversion_info}"
        
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
    
    for size, unit in test_cases:
        converted_size, converted_unit, info = convert_weight_to_oz(size, unit)
        print(f"\nInput:  size={size}, unit={unit}")
        print(f"Output: size={converted_size}, unit={converted_unit}")
        print(f"Info:   {info}")

