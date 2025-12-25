#!/usr/bin/env python3
"""
FULL LOAD - Process complete file (31,446 products)
This will take approximately 20-30 minutes with parallel processing
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from core.pipeline import Pipeline


def main():
    print("="*70)
    print("FULL LOAD - COMPLETE FILE PROCESSING")
    print("="*70)
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("\nERROR: OPENAI_API_KEY not set!")
        print("Please set your OpenAI API key in .env file")
        return
    
    filename = 'uncoded_amz_p5_2025.csv'
    
    print(f"\nFile: {filename}")
    print(f"Expected products: ~31,446")
    print(f"Estimated time: 20-30 minutes (with parallel processing)")
    print(f"Estimated cost: $0.50-$1.00 (depending on LLM usage)")
    
    print(f"\n{'='*70}")
    print("PROCESSING STAGES")
    print(f"{'='*70}")
    print("1. Load and preprocess data")
    print("2. Filter non-supplements (books, equipment, body care)")
    print("3. Keyword classification (fast, free)")
    print("4. Extract attributes (count, size, unit)")
    print("5. Validate classifications")
    print("6. LLM classification (for remaining products)")
    print("7. Final validation and output")
    
    response = input(f"\nProceed with full load? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("\nCancelled by user")
        return
    
    print(f"\n{'='*70}")
    print("STARTING PROCESSING")
    print(f"{'='*70}\n")
    
    # Create pipeline and process
    pipeline = Pipeline()
    pipeline.process_file(filename)
    
    print(f"\n{'='*70}")
    print("PROCESSING COMPLETE!")
    print(f"{'='*70}")
    print("\nOutput locations:")
    print("  - Logs: data/logs/amz_p5_2025/")
    print("  - Audit: data/audit/amz_p5_2025/")
    print("  - Final output: (to be added)")
    
    print("\nTo view status:")
    print("  python src/main.py --status")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

