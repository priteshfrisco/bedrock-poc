"""
Reasoning Builder - Tracks decision-making per product record

Builds human-readable reasoning strings showing:
- What was extracted
- What lookups were performed
- What rules were applied
- Any flags or issues
"""

from typing import Optional, List, Dict, Any


class ReasoningBuilder:
    """Builds reasoning strings for a single product"""
    
    def __init__(self, asin: str, title: str):
        self.asin = asin
        self.title = title
        self.parts: List[str] = []
        self.flags: List[str] = []
    
    def add(self, text: str):
        """Add a reasoning part"""
        self.parts.append(text)
    
    def add_flag(self, flag: str):
        """Add a flag (e.g., NEEDS_REVIEW, UNKNOWN_INGREDIENT)"""
        if flag not in self.flags:
            self.flags.append(flag)
    
    def build(self) -> str:
        """Generate final reasoning string"""
        if not self.parts:
            return "No reasoning recorded"
        
        reasoning = " ".join(self.parts)
        
        # Add flags if any
        if self.flags:
            reasoning += f" [FLAGS: {', '.join(self.flags)}]"
        
        return reasoning
    
    def needs_review(self) -> bool:
        """Check if this record needs manual review"""
        review_flags = ['NEEDS_REVIEW', 'UNKNOWN_INGREDIENT', 'FALLBACK_USED', 'UNKNOWN_CATEGORY']
        return any(flag in self.flags for flag in review_flags)

