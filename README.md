# Product Classification Pipeline

AI-powered supplement product classification system using GPT-5-mini.

## Quick Start

### 1. Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Add OpenAI API key to .env
echo "OPENAI_API_KEY=your_key_here" > .env
```

### 2. Run
```bash
# Place input CSV in data/input/
cp your_file.csv data/input/

# Update INPUT_FILE in src/main.py (line ~45)
INPUT_FILE = 'data/input/your_file.csv'

# Run pipeline
python src/main.py
```

### 3. Results
- **CSV Output**: `data/output/{filename}/run_{timestamp}/results.csv`
- **Audit Files**: `data/audit/{filename}/run_{timestamp}/final/*.json`
- **Logs**: `data/logs/{filename}/run_{timestamp}/*.log`
- **Status**: `data/tracking/files_status.json`

## Features

### Core Classification
- ✅ **Ingredients**: Extracted with category/subcategory via hybrid matching (Exact + Fuzzy + BM25)
- ✅ **Attributes**: Age, Gender, Form, Organic, Count, Size, Unit
- ✅ **Health Focus**: Primary ingredient-based lookup with title overrides
- ✅ **High Level Category**: PRIORITY VMS / NON-PRIORITY VMS / OTC / REMOVE
- ✅ **Business Rules**: 13 rules for category/subcategory refinement (Python post-processing)

### Performance
- ⚡ **100 parallel API calls** using ThreadPoolExecutor
- ⚡ **~2 min for 100 records** (~1,200 records/hour)
- ⚡ **Smart retry logic** for rate limits (exponential backoff)
- 💰 **~$0.002 per product**

### Tracking & Audit
- 📊 **File-level status tracking** (processing/completed/error)
- 📊 **Full audit trail** (per-product JSONs with LLM metadata)
- 📊 **Token breakdown** (input/output tokens for cost analysis)
- 📊 **Processing logs** (step-by-step execution logs)

## Project Structure

```
bedrock-poc/
├── src/
│   ├── main.py                    # Main entry point
│   ├── core/
│   │   ├── business_rules.py      # 13 business rules
│   │   ├── file_tracker.py        # File status tracking
│   │   ├── file_utils.py          # File I/O utilities
│   │   ├── high_level_category.py # HLC assignment
│   │   ├── log_manager.py         # Centralized logging
│   │   ├── preprocessing.py       # Non-supplement filtering
│   │   ├── reasoning_builder.py   # Reasoning string builder
│   │   └── unit_converter.py      # Weight conversion
│   ├── llm/
│   │   ├── gpt_client.py          # GPT-5-mini client
│   │   ├── prompt_builder.py      # Dynamic prompt builder
│   │   ├── response_schema.py     # JSON schema for LLM
│   │   └── tools/
│   │       ├── ingredient_lookup.py  # Hybrid matching
│   │       └── health_focus_lookup.py # HF lookup
│   └── pipeline/
│       └── step1_filter.py        # Non-supplement filter
│
├── reference_data/                # All lookup CSVs and rules JSONs
├── data/
│   ├── input/                     # Place input CSV here
│   ├── output/                    # Final CSV output
│   ├── audit/                     # Per-product audit JSONs
│   ├── logs/                      # Execution logs
│   └── tracking/                  # File status tracking
│       └── files_status.json      # Processing status database
│
├── requirements.txt
└── README.md
```

## Configuration

### Input File
Edit `INPUT_FILE` in `src/main.py` (line ~45):
```python
INPUT_FILE = 'data/input/your_file.csv'
```

### Required Columns
- `asin` (or UPC)
- `title` (product title)
- `brand` (brand name)

### Parallel Processing
Edit `MAX_WORKERS` in `src/main.py` (line ~48):
```python
MAX_WORKERS = 100  # Number of parallel API calls
```

## Output Format

### CSV Columns (45 total)
1-21: Core business data (UPC, Description, Brand, Category, Subcategory, Form, Age, Gender, etc.)
22-40: Additional ingredients (other ing. 2 - other ing. 20)
41-45: Reserved for future use (Spare1 - Spare5)

### Audit JSON
```json
{
  "asin": "B001234567",
  "title": "Turmeric Curcumin 1000mg Capsules",
  "brand": "Nature's Way",
  "status": "success",
  "category": "HERB FORMULAS",
  "subcategory": "TURMERIC",
  "primary_ingredient": "TURMERIC",
  "all_ingredients": ["TURMERIC", "CURCUMIN", "BLACK PEPPER"],
  "form": "Capsule",
  "age": "Adult",
  "gender": "Unisex",
  "health_focus": "Joint",
  "high_level_category": "PRIORITY VMS",
  "_metadata": {
    "api_cost": 0.0019,
    "tokens_used": 1234,
    "tokens": {
      "prompt": 800,
      "completion": 434
    },
    "processing_time_sec": 1.23
  }
}
```

## File Status Tracking

Check `data/tracking/files_status.json`:
```json
{
  "sample_100.csv": {
    "status": "completed",
    "last_run_id": "run_1",
    "completed_at": "2025-12-31T19:05:30.123Z",
    "total_records": 100,
    "success": 95,
    "filtered": 3,
    "errors": 2,
    "total_cost": 0.19,
    "total_tokens": 12000,
    "input_tokens": 8000,
    "output_tokens": 4000,
    "duration_seconds": 120.5
  }
}
```

## Re-running Files

The system prevents duplicate processing:
- If a file is currently `processing`, it will be skipped
- To re-run a completed file, either:
  1. Delete the entry from `files_status.json`, or
  2. Change status from `completed` to something else

## Cost Estimation

- **Per Product**: ~$0.002
- **100 Products**: ~$0.19
- **1,000 Products**: ~$1.90
- **10,000 Products**: ~$19.00

## Technical Details

### LLM Configuration
- **Model**: `gpt-5-mini`
- **Temperature**: 0.7
- **Max Tokens**: 2000
- **Response Format**: JSON with strict schema

### Hybrid Ingredient Matching
1. **Exact Match**: Direct string match
2. **Fuzzy Match**: RapidFuzz (threshold: 85%)
3. **BM25**: Best Match 25 for ranking (threshold: 5.0)
4. **LLM Fallback**: For uncertain matches

### Business Rules (Python Post-processing)
1. Herb formula detection
2. Protein categorization
3. Multivitamin refinement
4. Ingredient-specific overrides
5. Title-based overrides
6. 8 more rules...

## Troubleshooting

### Rate Limits
- System auto-retries with exponential backoff
- Reduce `MAX_WORKERS` if hitting limits frequently

### API Key Issues
```bash
# Verify .env file
cat .env

# Ensure OPENAI_API_KEY is set
export OPENAI_API_KEY=your_key_here
```

### Empty Results
- Check logs: `data/logs/{filename}/run_{timestamp}/run.log`
- Check audit files for errors

## License

Proprietary - Nature's Way


