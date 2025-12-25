"""
Pipeline Orchestrator - Coordinates the entire classification workflow

Responsibilities:
- Coordinates all components (storage, preprocessing, filtering)
- Handles ALL logging and file management
- Tracks progress and errors
- Creates proper folder structure (logs/audit with run_N)

Components do NOT log or create files - pipeline does everything.

CURRENT STATUS: STOPS AFTER FILTERING
"""

import pandas as pd

from clients.storage_client import create_storage_client_from_env
from clients.file_tracker import create_file_tracker_from_env
from core.file_logger import create_file_logger
from core.preprocessor import standardize_dataframe
from knowledge.subcategory_filter import create_subcategory_filter


class Pipeline:
    
    def __init__(self):
        self.storage = create_storage_client_from_env()
        self.tracker = create_file_tracker_from_env()
    
    def process_file(self, filename: str):
        print(f"\n{'='*70}")
        print(f"PROCESSING: {filename}")
        print(f"{'='*70}")
        
        raw_df = self.storage.read_csv(filename)
        total_products = len(raw_df)
        
        print(f"\nLoaded: {total_products:,} products")
        
        logger = create_file_logger(filename)
        
        print(f"Run: {logger.run_id}")
        print(f"Logs: {logger.logs_path}")
        print(f"Audit: {logger.audit_path}")
        
        self.tracker.start_processing(filename, total_products)
        
        try:
            with logger:
                clean_df = self._step1_preprocess(raw_df)
                
                supplements_df, removed_df, removed_count = self._step2_filter_subcategories(
                    clean_df, logger
                )
                
                print(f"\n{'='*70}")
                print(f"FILTERING COMPLETE - READY FOR LLM CLASSIFICATION")
                print(f"{'='*70}")
                print(f"Products passed filtering: {len(supplements_df):,}")
                print(f"Products removed: {removed_count:,}")
                print(f"\nNext step: Send {len(supplements_df):,} products to LLM for classification")
                
                final_summary = {
                    'total_products': total_products,
                    'removed': removed_count,
                    'supplements_passed': len(supplements_df),
                    'step1_subcategory_filtering': {
                        'removed': removed_count,
                        'passed_forward': len(supplements_df)
                    }
                }
                logger.write_final_summary(final_summary)
                
                self.tracker.complete_processing(
                    filename,
                    removed_count=removed_count,
                    classified_count=0  # Classification not done yet
                )
            
            print(f"\n{'='*70}")
            print(f"PROCESSING COMPLETE")
            print(f"{'='*70}")
            print(f"Total: {total_products:,}")
            print(f"Removed: {removed_count:,}")
            print(f"Supplements ready for LLM: {len(supplements_df):,}")
            
        except Exception as e:
            print(f"\nERROR: {e}")
            self.tracker.mark_failed(filename, str(e))
            raise
    
    def _step1_preprocess(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        print(f"\nStep 1: Preprocessing...")
        clean_df = standardize_dataframe(raw_df)
        print(f"Standardized {len(clean_df):,} products")
        return clean_df
    
    def _step2_filter_subcategories(
        self,
        clean_df: pd.DataFrame,
        logger
    ) -> tuple:
        step_name = 'step1_subcategory_filtering'
        
        print(f"\nStep 2: Filtering subcategories...")
        
        logger.log_step(step_name, "="*50)
        logger.log_step(step_name, "STEP 1: SUBCATEGORY FILTERING")
        logger.log_step(step_name, "="*50)
        logger.log_step(step_name, f"Input: {len(clean_df):,} products")
        
        subcategory_filter = create_subcategory_filter()
        
        supplements_df, removed_df, stats = subcategory_filter.filter_dataframe(clean_df)
        
        logger.log_step(step_name, "")
        logger.log_step(step_name, "Results:")
        logger.log_step(step_name, f"  Removed by subcategory:   {stats['removed_by_subcategory']:,}")
        logger.log_step(step_name, f"  Removed by title keyword: {stats['removed_by_title']:,}")
        logger.log_step(step_name, f"  Total removed:            {stats['removed']:,}")
        logger.log_step(step_name, f"  Not in lookup (kept):     {stats['not_in_lookup']:,}")
        logger.log_step(step_name, f"  Remapped (supplements):   {stats['remapped']:,}")
        logger.log_step(step_name, f"  Total passed forward:     {stats['passed_forward']:,}")
        logger.log_step(step_name, "")
        
        # Save unknown subcategories with product examples
        if stats['unknown_subcategories']:
            logger.log_step(step_name, "Anomalies - Unknown subcategories:")
            for subcat, count in sorted(stats['unknown_subcategories'].items(), key=lambda x: x[1], reverse=True):
                logger.log_step(step_name, f"  - '{subcat}': {count} product(s)")
            logger.log_step(step_name, "")
            
            # Save unknown subcategories to run-specific audit folder with product samples
            unknown_file_path = logger.audit_path / 'unknown_subcategories.csv'
            review_file = subcategory_filter.save_unknown_subcategories_for_review(
                stats['unknown_subcategories'],
                stats['unknown_subcategory_products'],
                output_file=str(unknown_file_path)
            )
            logger.log_step(step_name, f"Unknown subcategories saved: audit/{logger.file_id}/{logger.run_id}/unknown_subcategories.csv")
            print(f"  Unknown subcategories saved to audit folder with product samples")
            logger.log_step(step_name, "")
        
        # Save removed products - split by removal method
        if len(removed_df) > 0:
            essential_cols = ['asin', 'brand', 'title', 'amazon_subcategory', 'reasoning', 'removal_method']
            removed_clean = removed_df[essential_cols]
            
            # Save all removed products
            logger.write_step_csv(step_name, removed_clean, 'removed_all.csv')
            logger.log_step(step_name, f"All removed products: audit/{logger.file_id}/{logger.run_id}/{step_name}/removed_all.csv")
            
            # Save subcategory-filtered products separately
            subcategory_removed = removed_clean[removed_clean['removal_method'] == 'subcategory'].copy()
            if len(subcategory_removed) > 0:
                subcategory_removed_display = subcategory_removed[['asin', 'brand', 'title', 'amazon_subcategory', 'reasoning']]
                logger.write_step_csv(step_name, subcategory_removed_display, 'removed_by_subcategory.csv')
                logger.log_step(step_name, f"Subcategory removals: audit/{logger.file_id}/{logger.run_id}/{step_name}/removed_by_subcategory.csv")
            
            # Save title-filtered products separately
            title_removed = removed_clean[removed_clean['removal_method'] == 'title'].copy()
            if len(title_removed) > 0:
                title_removed_display = title_removed[['asin', 'brand', 'title', 'amazon_subcategory', 'reasoning']]
                logger.write_step_csv(step_name, title_removed_display, 'removed_by_title_keyword.csv')
                logger.log_step(step_name, f"Title keyword removals: audit/{logger.file_id}/{logger.run_id}/{step_name}/removed_by_title_keyword.csv")
        
        logger.log_step(step_name, "="*50)
        
        print(f"Filtered: {stats['removed']:,} removed ({stats['removed_by_subcategory']:,} subcategory + {stats['removed_by_title']:,} title), {stats['passed_forward']:,} passed")
        
        return supplements_df, removed_df, stats['removed']


def process_file(filename: str):
    pipeline = Pipeline()
    pipeline.process_file(filename)


def process_all_files():
    pipeline = Pipeline()
    files = pipeline.storage.list_input_files()
    
    for filename in files:
        if not pipeline.tracker.is_file_processed(filename):
            pipeline.process_file(filename)

