#!/usr/bin/env python3
"""
Main Entry Point - Product Classification Pipeline

Usage:
    python src/main.py --file uncoded_amz_p5_2025.csv
    python src/main.py --process-all
    python src/main.py --status
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.pipeline import process_file, process_all_files
from clients.file_tracker import create_file_tracker_from_env
from clients.storage_client import create_storage_client_from_env


def show_status():
    tracker = create_file_tracker_from_env()
    storage = create_storage_client_from_env()
    
    print("\n" + "="*70)
    print("PIPELINE STATUS")
    print("="*70)
    
    summary = tracker.get_summary()
    
    print(f"\nProcessing Summary:")
    print(f"   Completed: {summary['completed']}")
    print(f"   Processing: {summary['processing']}")
    print(f"   Failed: {summary['failed']}")
    print(f"   Total Products Processed: {summary['total_products_processed']:,}")
    print(f"   Total Removed: {summary['total_removed']:,}")
    print(f"   Total Classified: {summary['total_classified']:,}")
    
    files = storage.list_input_files()
    
    if files:
        print(f"\nInput Files ({len(files)} total):")
        for filename in files:
            status = tracker.get_file_status(filename)
            if status:
                status_icon = {
                    'completed': '[DONE]',
                    'processing': '[...]',
                    'failed': '[FAIL]'
                }.get(status['status'], '[?]')
                print(f"   {status_icon} {filename} - {status['status']}")
            else:
                print(f"   [NEW] {filename} - not processed")
    
    print("\n" + "="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Product Classification Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main.py --file uncoded_amz_p5_2025.csv    Process single file
  python src/main.py --process-all                     Process all unprocessed files
  python src/main.py --status                          Show processing status
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', type=str, help='Process a specific file')
    group.add_argument('--process-all', action='store_true', help='Process all unprocessed files')
    group.add_argument('--status', action='store_true', help='Show processing status')
    
    args = parser.parse_args()
    
    try:
        if args.status:
            show_status()
        elif args.file:
            process_file(args.file)
        elif args.process_all:
            process_all_files()
    
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

