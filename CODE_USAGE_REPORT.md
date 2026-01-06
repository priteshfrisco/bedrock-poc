# Code Usage Report

## ✅ ACTIVELY USED

### Core (`src/core/`)
- ✅ `preprocessing.py` - Data standardization, non-supplement detection
- ✅ `log_manager.py` - Logging and audit file management
- ✅ `file_utils.py` - CSV writing utilities
- ✅ `file_tracker.py` - File-level status tracking (local mode)
- ✅ `result_builder.py` - Building result dictionaries (local mode)

### LLM (`src/llm/`)
- ✅ `gpt_client.py` - OpenAI API interaction with tool calling
- ✅ `prompt_builder.py` - Dynamic prompt generation
- ✅ `response_schema.py` - JSON schema for structured outputs
- ✅ `tools/__init__.py` - Tool registry
- ✅ `tools/ingredient_lookup.py` - BM25/fuzzy ingredient search
- ✅ `tools/business_rules_tool.py` - LLM-callable business rules
- ✅ `tools/health_focus_lookup.py` - Health benefits mapping
- ✅ `utils/error_handler.py` - Error handling utilities

### Pipeline (`src/pipeline/`)
- ✅ `step1_filter.py` - Non-supplement filtering
- ✅ `step2_llm.py` - LLM extraction orchestration
- ✅ `step3_postprocess.py` - Post-processing logic
- ✅ `utils/business_rules.py` - Category/subcategory rules engine
- ✅ `utils/high_level_category.py` - High-level category mapping
- ✅ `utils/unit_converter.py` - Size/count/unit parsing

### AWS (`src/aws/`)
- ✅ `s3_manager.py` - S3 read/write operations
- ✅ `dynamodb_manager.py` - DynamoDB state tracking
- ✅ `notification.py` - SNS email notifications

### Main
- ✅ `main.py` - Unified orchestrator (local + AWS modes)

---

## ❌ NOT CURRENTLY USED

### Core (`src/core/`)
- ❌ `db_manager.py` 
  - **Why:** Was for SQLite, replaced by `aws/dynamodb_manager.py` for AWS
  - **Keep?** Yes, useful for local mode database tracking
  
- ❌ `reasoning_builder.py`
  - **Why:** Reasoning now comes from LLM's `business_rules` tool
  - **Keep?** Yes, could be useful for custom reasoning augmentation

---

## 📊 SUMMARY

**Total Files:** 25
**Used:** 23 (92%)
**Unused:** 2 (8%)

**Notes:**
- All unused files are in `src/core/` and were legacy features
- `db_manager.py` could be reactivated for local SQLite tracking
- `reasoning_builder.py` could enhance LLM reasoning with custom logic
- No cleanup needed - keeping these for potential future use

---

## 🔧 RECENT REFACTORING

1. **Extracted notification code** from `main.py` → `aws/notification.py`
2. **Restored features:**
   - Audit logging (was lost in parallel processing)
   - Folder structure (`{filename}/run_1/`)
   - Heartbeat (DynamoDB progress updates)
   - Filename validation (`uncoded_*`)
3. **Added parallel processing:** 100 concurrent workers for speed

