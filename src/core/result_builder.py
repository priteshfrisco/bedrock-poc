"""
Result Builder - DRY helper for building result dictionaries
"""

from datetime import datetime
from typing import Dict, Any


def build_error_result(
    result: Dict[str, Any],
    error_message: str,
    step_completed: int,
    start_time: datetime
) -> Dict[str, Any]:
    """
    Build error result dictionary (DRY)
    
    Args:
        result: Base result dict
        error_message: Error message
        step_completed: Which step failed
        start_time: Process start time
    
    Returns:
        Updated result dict
    """
    result['status'] = 'error'
    result['error'] = error_message
    result['step_completed'] = step_completed
    result['processing_time_sec'] = (datetime.now() - start_time).total_seconds()
    return result


def build_success_result(
    result: Dict[str, Any],
    step_completed: int,
    start_time: datetime,
    **attributes
) -> Dict[str, Any]:
    """
    Build success result dictionary (DRY)
    
    Args:
        result: Base result dict
        step_completed: Which step completed
        start_time: Process start time
        **attributes: Additional attributes to add
    
    Returns:
        Updated result dict
    """
    result['status'] = 'success'
    result['step_completed'] = step_completed
    result['processing_time_sec'] = (datetime.now() - start_time).total_seconds()
    result.update(attributes)
    return result


def build_filtered_result(
    result: Dict[str, Any],
    filter_reason: str,
    filter_type: str,
    start_time: datetime,
    lookup_action: str = None
) -> Dict[str, Any]:
    """
    Build filtered result dictionary (DRY)
    
    Args:
        result: Base result dict
        filter_reason: Why it was filtered
        filter_type: 'filtered_by_remove' or 'filtered_by_keyword'
        start_time: Process start time
        lookup_action: Optional lookup action (REMAP, UNKNOWN, etc.)
    
    Returns:
        Updated result dict
    """
    result['status'] = filter_type
    result['step_completed'] = 1
    result['filter_reason'] = filter_reason
    result['category'] = 'REMOVE'
    result['high_level_category'] = 'REMOVE'
    result['processing_time_sec'] = (datetime.now() - start_time).total_seconds()
    
    if lookup_action:
        result['lookup_action'] = lookup_action
    
    return result

