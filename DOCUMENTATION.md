# Bedrock AI Data Enrichment System

## Introduction

This application is deployed on AWS cloud infrastructure and processes supplement product data using AI.

The system runs as a Docker container on **AWS ECS Fargate** with dedicated compute resources (4 vCPU, 8GB RAM). When you upload a CSV file to S3, a Lambda function detects it and automatically launches an ECS Fargate task to process the data. Once processing completes, the task shuts down.

All data is stored in a single S3 bucket organized into folders:

- **input/**: Where you upload CSV files to be processed
- **output/**: Where the enriched/coded data is saved
- **audit/**: Stores detailed JSON logs of every AI decision made
- **logs/**: Contains processing logs and system information
- **reference/**: Stores lookup tables (ingredient database, business rules, etc.)

The AI processing uses **OpenAI's GPT models** (via API). When a product needs to be analyzed, the system sends the product information to OpenAI, which returns structured data about ingredients, categories, forms, and other details. The OpenAI API key is securely stored in AWS Secrets Manager.

**DynamoDB** is used to track the processing state of each product, ensuring no duplicates and allowing you to resume if processing is interrupted.

**SNS (Simple Notification Service)** sends email notifications when processing starts and completes, so you know exactly when your data is ready.

You can monitor real-time progress and logs through **CloudWatch**, which captures all system output and processing details.

The Docker image is stored in **AWS ECR (Elastic Container Registry)**, making it easy to update the application code by simply pushing a new image.

---

## How It Works

When you upload a CSV file to the **input/** folder in the S3 bucket, here's what happens:

1. **File Detection**: A Lambda function is triggered when your file lands in S3.
2. **Task Launch**: The Lambda function starts an ECS Fargate task to process the file.
3. **Container Startup**: The Fargate task pulls the Docker image from ECR and starts the application with 4 vCPUs and 8GB of RAM.
4. **Data Loading**: The application downloads your CSV file from S3 and reads the product rows. It also downloads reference data from the **reference/** folder.
5. **Start Notification**: An email is sent via SNS letting you know processing has started and how many products will be processed.
6. **Processing Loop**: For each product in your CSV, the system runs through 3 steps (details below):

   - Step 1: Filter non-supplements
   - Step 2: LLM extraction
   - Step 3: Post-processing

   After each product is processed, update DynamoDB to mark it as complete
7. **Output Generation**: After all products are processed, create an enriched CSV file and upload it to the **output/** folder.
8. **Success Notification**: An email is sent via SNS with the processing results, statistics, and links to download your output file.
9. **Cleanup**: The Fargate task shuts down.

**If anything fails**: An error notification email is sent via SNS with details about what went wrong and where to check CloudWatch logs.

All logs are sent to CloudWatch during processing.

### Process Flow Diagram

```
┌─────────────────┐
│  Upload CSV to  │
│  S3 input/      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Lambda Triggered│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Start Fargate  │
│      Task       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Download CSV   │
│  & Reference    │
│      Data       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  For Each Row:  │
│  ┌───────────┐  │
│  │ DynamoDB  │  │
│  │   Check   │  │
│  └─────┬─────┘  │
│        │        │
│        ▼        │
│  ┌───────────┐  │
│  │  OpenAI   │  │
│  │    API    │  │
│  └─────┬─────┘  │
│        │        │
│        ▼        │
│  ┌───────────┐  │
│  │   Save    │  │
│  │   Audit   │  │
│  └───────────┘  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Upload Output   │
│   to S3 output/ │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Send Email via │
│       SNS       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Task Shutdown  │
└─────────────────┘
```

---

## Input File Format

Your input CSV file must start with `uncoded_` in the filename (e.g., `uncoded_products.csv`, `uncoded_january_2026.csv`)

**Required columns** (system will only process these):

- `ASIN/UPC Key` - Product identifier
- `MI: Brand` - Brand name
- `MI: Description` - Product title/description
- `Source Subcategory Trx` - Amazon subcategory

**Optional columns** (pass-through, not processed but preserved in output):

- `Product_ID` - Internal product ID
- `Source Category Trx` - Amazon category (parent level)
- `Dollars in USD` - Sales data
- Any other custom columns

**Example input file (uncoded_products.csv):**

| Product_ID | ASIN/UPC Key | MI: Brand      | MI: Description                              | Source Category Trx | Source Subcategory Trx            | Dollars in USD |
| ---------- | ------------ | -------------- | -------------------------------------------- | ------------------- | --------------------------------- | -------------- |
| 1          | B001ABC123   | Nature Made    | Vitamin D3 5000 IU Softgels 100 Count        | Health & Household  | vitamin d nutritional supplements | 15432.50       |
| 2          | B002XYZ456   | Garden of Life | Women's Multivitamin 50+ Organic 120 Tablets | Health & Household  | multivitamins                     | 28901.75       |
| 3          | B003DEF789   | NOW Foods      | Fish Oil 1000mg Omega-3 200 Softgels         | Health & Household  | fish oils nutritional supplements | 9876.25        |
| 4          | B004GHI012   | Random Books   | Complete Guide to Vitamins and Supplements   | Books               | books                             | 542.00         |

**Note:** The system internally renames columns: `ASIN/UPC Key` → `asin`, `MI: Brand` → `brand`, `MI: Description` → `title`, `Source Subcategory Trx` → `amazon_subcategory`

---

## Output File Columns

### What the R System Extracted vs. What Our LLM Code Extracts

**Original R System (15 columns extracted by automated scripts):**

The R system used 7 separate scripts (Ingredient, Form, Age, Gender, Count, Size, Health Focus) with ML models (Random Forest, XGBoost) and regex patterns to extract:

1. **Functional Ingredient** - Primary ingredient (rule-based lookup)
2. **RetailerSku** - ASIN from input
3. **Age** - Random Forest ML model
4. **Count** - Regex pattern matching
5. **Unit Of Measurement** - Regex pattern matching
6. **Form** - Random Forest ML model
7. **Category** - Nature's Way category
8. **Subcategory** - Nature's Way subcategory
9. **Gender** - Random Forest ML model
10. **Health Focus** - XGBoost ML model
11. **Title** - Product title from input
12. **Brand** - Brand name from input
13. **Size** - Regex pattern matching (pack count)
14. **Organic** - Keyword detection
15. **High Level Category** - Priority VMS / Non-Priority VMS / OTC / REMOVE

**Manual Analyst Work (11 columns added, 1-3 days):**

Analysts manually added these columns to create the final Master Item File (26 total columns):

- **UPC** - Manual lookup (not in Amazon data)
- **NW Sub Brand 1, 2, 3** - Manual entry (Nature's Way internal only)
- **Potency** - Manual extraction (mainly for probiotics)
- **Company** - Parent company (manual refinement)
- **NW_UPC** - Nature's Way internal UPC (NW/IT only)
- **Reasoning** - Manual notes about corrections made

Plus renaming columns to match Master Item File format.

---

**Our New LLM-Based System** 

Our system extracts columns using GPT-5-mini with tool calling, eliminating the need for most manual work:

| Column                              | Extraction Method                              | R System Equivalent                          |
| ----------------------------------- | ---------------------------------------------- | -------------------------------------------- |
| `RetailerSku`                     | From input (ASIN)                              | Same                                         |
| `UPC`                             | Empty (manual lookup still required)           | Same (manually added)                        |
| `Description`                     | From input (title)                             | Title                                        |
| `Brand`                           | From input                                     | Same                                         |
| **`NW Category`**           | **LLM + tool calling + business rules**  | Category (ML model)                          |
| **`NW Subcategory`**        | **LLM + tool calling + business rules**  | Subcategory (ML model)                       |
| `NW Sub Brand 1, 2, 3`            | Empty (manual entry for NW/IT)                 | Same (manually added)                        |
| **`Potency`**               | **LLM extraction (Step 9)**              | **Manually added by analysts** ✨ NEW! |
| **`FORM`**                  | **LLM extraction (Step 3)**              | Form (Random Forest ML)                      |
| **`AGE`**                   | **LLM extraction (Step 1)**              | Age (Random Forest ML)                       |
| **`GENDER`**                | **LLM extraction (Step 2)**              | Gender (Random Forest ML)                    |
| `COMPANY`                         | Default to brand (manual refinement)           | Same (manually added)                        |
| **`FUNCTIONAL INGREDIENT`** | **LLM + tool calling (Step 8)**          | Functional Ingredient (rule-based)           |
| **`HEALTH FOCUS`**          | **Lookup via primary ingredient**        | Health Focus (XGBoost ML)                    |
| **`SIZE`**                  | **LLM extraction (Step 7) + conversion** | Size/Count (regex patterns)                  |
| **`HIGH LEVEL CATEGORY`**   | **Rule-based assignment**                | Same                                         |
| `NW_UPC`                          | Empty (NW/IT internal only)                    | Same (manually added)                        |
| **`Unit of Measure`**       | **LLM extraction (Step 6) + conversion** | Unit (regex patterns)                        |
| **`Pack Count`**            | **LLM extraction (Step 5)**              | **Manually verified** ✨ NEW!          |
| **`Organic`**               | **LLM extraction (Step 4)**              | Organic (keyword detection)                  |
| **`Reasoning`**             | **Auto-generated from business rules**   | Manual notes                                 |

**Key Improvements Over R System:**

✅ **Potency** - Now automatically extracted (was manual in R system)
✅ **Pack Count** - Now automatically extracted (was manual verification in R system)
✅ **Reasoning** - Automatically generated with full audit trail
✅ **Single LLM Pass** - All attributes extracted together (vs. 7 separate R scripts)
✅ **Tool Calling** - Dynamic ingredient lookup with normalized names
✅ **Business Rules** - Applied in post-processing (Python) instead of manual fixes
✅ **Audit Trail** - Full JSON audit files with LLM reasoning and token usage

**What Still Requires Manual Work:**

- `UPC` - Manual lookup (not in Amazon data)
- `NW Sub Brand 1, 2, 3` - Manual entry (Nature's Way internal only)
- `Company` - Manual refinement for parent companies
- `NW_UPC` - Manual entry (Nature's Way internal only)

**Total Manual Work Reduction: ~80-90%**

The R system required 1-3 days of manual post-processing by analysts. Our LLM system reduces this to ~1-2 hours for manual UPC lookups and sub-brand entries only.

---

## Step 1: Non-Supplement Filtering

This step filters out products that are not supplements before sending them to the AI. It uses two reference files stored in the **reference/** folder.

### How Step 1 Works

1. Look up the product's Amazon subcategory in `amazon_subcategory_lookup.csv`
2. If action = **REMOVE**, filter out immediately
3. If action = **REMAP** or **UNKNOWN**, check the product title for non-supplement keywords
4. If a keyword matches, filter out the product
5. If no keyword matches, pass to Step 2 (LLM processing)

### Reference File 1: amazon_subcategory_lookup.csv

This file maps Amazon subcategories to actions.

**Columns used by the system:**

- `amazon_subcategory` - The Amazon subcategory value (must match exactly, lowercase)
- `action` - What to do: **REMOVE** (filter out) or **REMAP** (assign category)
- `nw_category` - Category to assign if action = REMAP
- `nw_subcategory` - Subcategory to assign if action = REMAP
- `notes` - Explanation shown in filter reason

**Other columns** (old_nw_category, old_nw_subcategory, change_source, change_notes) are ignored by the system and only for documentation.

**Example rows:**

| amazon_subcategory                | action | nw_category               | nw_subcategory  | notes                   |
| --------------------------------- | ------ | ------------------------- | --------------- | ----------------------- |
| vitamin d nutritional supplements | REMAP  | BASIC VITAMINS & MINERALS | LETTER VITAMINS | Maps to Vitamin D       |
| fish oils nutritional supplements | REMAP  | SPECIALTY SUPPLEMENTS     | FISH OILS       | Maps to Fish Oils       |
| multivitamins                     | REMAP  | COMBINED MULTIVITAMINS    | MULTIVITAMINS   | Maps to Multivitamins   |
| acne & blemish treatments         | REMOVE |                           |                 | Non-supplement category |
| books                             | REMOVE |                           |                 | Non-supplement category |
| aromatherapy & essential oils     | REMOVE |                           |                 | Non-supplement category |

### Reference File 2: non_supplement_keywords.csv

This file defines keywords that identify non-supplement products.

**Columns used by the system:**

- `keyword` - The keyword to check in product titles (case insensitive, whole word matching)
- `auto_variations` - If **yes**, automatically generates variations (plural, e-prefix, hyphen/space)
- `exceptions` - Comma-separated list of exception words. If title contains any exception, don't filter

**Other columns** (category, notes) are ignored by the system and only for documentation.

**Examples:**

```csv
keyword,auto_variations,exceptions,notes
book,yes,,Catches books/ebook/e-book etc
essential oil,yes,"supplement,capsule,softgel",Keep if supplement form
shirt,yes,,Clothing items
test kit,yes,,Testing devices and kits
```

**How auto_variations works:**

- `book` with auto_variations=yes generates: `books`, `ebook`, `e-book`, `e book`
- `test kit` with auto_variations=yes generates: `test-kit`, `testkit`

**How exceptions work:**

- "Essential Oil Blend" → **FILTERED** (no exception word found)
- "Essential Oil Capsules" → **PASSES** (has "capsule" exception)
- "Fish Oil Softgels" → **PASSES** (has "softgel" exception)

### Audit Files Created in Step 1

Step 1 creates detailed audit files in the **audit/** folder to help you understand filtering decisions:

**Individual Product Audits:**

- `audit/step1_filter/{asin}.json` - JSON file for each filtered product with details

**
    Summary Files:**

1. `records_filtered_by_remove.csv` - Products filtered because their Amazon subcategory has action=REMOVE

   - Columns: asin, title, brand, amazon_subcategory, action, reason
2. `records_filtered_by_keyword.csv` - Products filtered by keyword matching

   - Columns: asin, title, brand, amazon_subcategory, lookup_action, filter_reason, matched_keyword
3. `records_remap.csv` - Products that passed filtering and will use REMAP category

   - Columns: asin, title, brand, amazon_subcategory, action, nw_category, nw_subcategory, remap_reason
4. `records_unknown.csv` - Products with unknown Amazon subcategory that passed filtering

   - Columns: asin, title, brand, amazon_subcategory, reason
5. `step1_statistics.json` - Overall statistics with counts, percentages, and breakdowns

**Logs:**

- `logs/step1_filter.log` - Real-time processing log showing each product checked and filtering decisions

### Updating Reference Files

If you need to add new subcategories or keywords:

1. Edit the CSV file locally
2. Upload the updated file to S3 bucket **reference/** folder
3. The next processing run will automatically use the updated file

## Step 2: LLM Extraction

Products that passed Step 1 filtering are sent to OpenAI for attribute extraction. The system processes 200 products in parallel for speed.

### What Step 2 Does

For each product, the system:

1. **Check DynamoDB**: See if this product was already processed (prevents duplicates if processing is interrupted)
2. **Build Prompt**: Create a detailed prompt with the product title and extraction rules from reference files
3. **Send to OpenAI**: Call OpenAI GPT API with the prompt and two tools:

   - `lookup_ingredient` - Searches the ingredient database
   - `apply_business_rules` - Applies category assignment logic
4. **OpenAI Extracts Attributes** step-by-step:

   - **Safety Check**: Is this actually a supplement? If not, return "REMOVE" for all fields
   - **Step 1 - Age**: Target age group (e.g., "AGE GROUP - MATURE ADULT", "AGE GROUP - KIDS", "N/A")
   - **Step 2 - Gender**: Target gender (e.g., "GENDER - FEMALE", "GENDER - MALE", "N/A")
   - **Step 3 - Form**: Physical form (e.g., "CAPSULE", "SOFTGEL", "TABLET", "POWDER")
   - **Step 4 - Organic**: Organic status ("ORGANIC", "NOT ORGANIC", "N/A")
   - **Step 5 - Size (Quantity)**: How many units per container (e.g., "60", "120", "180")
   - **Step 6 - Unit**: Type of unit ("COUNT" for capsules/tablets, "oz" for liquids, "lb"/"g"/"kg" for powders)
   - **Step 7 - Pack Count**: Number of containers in pack (e.g., "1", "2", "3")
   - **Step 8 - Potency**: Dosage/strength (e.g., "5000 IU", "1000mg")
   - **Step 9 - Ingredients & Business Rules**:
     - Extract all functional ingredients from the title
     - For each ingredient, call `lookup_ingredient` tool to get category/subcategory
     - Call `apply_business_rules` tool with all ingredients to determine final category and subcategory
5. **Validate Response**: Check if OpenAI returned "REMOVE" for any critical attribute (means non-supplement detected)
6. **Save Results**:

   - Save audit JSON file for this product
   - Update DynamoDB with status (success/filtered/error)
   - Track token usage and API cost

### Reference Files Used in Step 2

The LLM prompt is built from these reference files in the **reference/** folder:

1. `general_instructions.json` - General prompt templates (output format, workflow instructions, false positive warnings)
2. `safety_check_instructions.json` - Safety check template with hard-coded examples of supplements vs non-supplements
3. `non_supplement_keywords.csv` - Safety check keywords grouped by category (books, DVDs, apparel, etc.)
4. `age_extraction_rules.json` - Rules for extracting target age group
5. `gender_extraction_rules.json` - Rules for extracting target gender
6. `form_extraction_rules.json` - Rules for extracting physical form (capsule, tablet, etc.)
7. `form_priority_rules.json` - Priority rules when multiple forms are detected
8. `organic_extraction_rules.json` - Rules for determining organic status
9. `pack_count_extraction_rules.json` - Rules for extracting pack size
10. `unit_extraction_rules.json` - Rules for extracting unit of measurement
11. `size_extraction_rules.json` - Rules for extracting quantity per unit
12. `ingredient_extraction_rules.json` - Rules for extracting functional ingredients (critical rules, exclusions, special handling, combo detection, context-dependent lookups)
13. `ingredient_category_lookup.csv` - Database of 920+ ingredients with category/subcategory mappings (used by `lookup_ingredient()` tool)
14. `potency_extraction_rules.json` - Rules for extracting dosage/strength
15. `business_rules.json` - 5 business rules for final category/subcategory determination (used by `apply_business_rules()` tool)
16. `postprocessing_rules.json` - Post-processing rules for ingredient combos and high-level category mapping (used by `apply_postprocessing()` tool)

### Audit Files Created in Step 2

For each product processed:

- `audit/{file_id}/{run_id}/step2_llm/{asin}.json` - Complete extraction result including all attributes, ingredients, business rules applied, token usage, and API cost

**What's in the audit file:**

- Product details (ASIN, title, brand)
- All extracted attributes (age, gender, form, organic, pack count, unit, size, potency)
- Ingredient list with category/subcategory mappings
- Business rules applied and category changes
- LLM reasoning for each extraction decision
- Token usage and API cost

### Logs Created in Step 2

Real-time processing logs stored in the **logs/{file_id}/{run_id}/** folder:

- `step2_llm.log` - Detailed log of LLM extraction process
  - LLM calls for each product
  - Token usage statistics
  - API response times
  - Safety check decisions (products marked as REMOVE)
  - Business rules application
  - Warnings and errors

**Example log entries:**

```
[2025-01-08T10:30:15.123Z] [ASIN123] Starting LLM extraction...
[2025-01-08T10:30:16.456Z] [ASIN123] LLM extraction complete (tokens: 1250)
[2025-01-08T10:30:17.789Z] [ASIN456] LLM detected non-supplement (returned REMOVE for attributes)
```

### Updating Reference Files

To modify extraction rules:

1. Edit the JSON file locally with your changes
2. Upload the updated file to S3 bucket **reference/** folder
3. The next processing run will automatically use the updated rules

**Note:** Changes to these files will affect how the LLM extracts attributes. Test changes carefully on a small batch first.

### 2.1 LLM Safety Check (Before Attribute Extraction)

Before extracting any attributes, the LLM performs a critical safety check to catch non-supplements that may have passed Step 1 filtering.

**How It Works:**

1. **Check Product Title**: The LLM reads the product title and checks if it contains non-supplement keywords
2. **Apply Exception Rules**: If exception words are present (e.g., "capsule", "supplement", "softgel"), the product is NOT filtered
3. **Return REMOVE**: If the LLM determines this is a non-supplement, it returns "REMOVE" for age, gender, and form attributes
4. **System Detects REMOVE**: The system checks if any of these attributes = "REMOVE"
5. **Filter Product**: If REMOVE is detected, mark all fields as "REMOVE" and save as filtered

**Safety Check Keywords:**

The safety check uses `non_supplement_keywords.csv` file, grouped by categories:

- Keywords are organized by category (jewelry, body_care, books_media, equipment, apparel, topical_oils, food)
- The LLM sees keywords grouped by category for better context
- Exceptions are shown inline (e.g., "essential oil" + supplement/capsule/softgel = Keep)

The LLM makes intelligent decisions:

- Understands context better than simple keyword matching
- Applies exceptions automatically (e.g., "Fish Oil Softgels" is kept even though it contains "oil")
- Can detect ambiguous cases (e.g., "Protein Bar" vs "Chocolate Bar")

**Example:**

- Title: "Nutrition Book Guide"
- LLM sees "book" in Books/Media category → Returns all "REMOVE" → Product filtered
- Title: "Fish Oil Softgels 1000mg"
- LLM sees "essential oil" but also "softgels" (exception) → Processes normally

**How to Modify the Safety Check:**

The safety check prompt is built from TWO files:

**File 1: `reference_data/non_supplement_keywords.csv`** (keywords and exceptions)

**Columns:**

- `keyword` - The keyword to check (e.g., "book", "essential oil", "lotion")
- `category` - Group name (e.g., "books_media", "topical_oils", "body_care")
- `auto_variations` - "yes" or "no" (generates plural, e-prefix, hyphen variations)
- `exceptions` - Comma-separated exception words (e.g., "supplement,capsule,softgel")
- `notes` - Description for reference

**Example rows:**

| keyword       | category     | auto_variations | exceptions                 | notes                                              |
| ------------- | ------------ | --------------- | -------------------------- | -------------------------------------------------- |
| book          | books_media  | yes             |                            | Catches books/ebook/e-book etc (generates plurals) |
| shampoo       | body_care    | no              |                            | Hair care products (no variations needed)          |
| essential oil | topical_oils | yes             | supplement,capsule,softgel | Keep if supplement form (e.g. Fish Oil Softgels)   |
| lotion        | body_care    | yes             |                            | Body lotions (generates lotions plural)            |
| machine       | equipment    | no              |                            | Equipment/devices (exact match only)               |
| test kit      | equipment    | yes             |                            | Testing devices (generates test-kit, testkit)      |

**How to Modify:**

To add or change non-supplement keywords:

1. **Download the file** from S3: `reference_data/non_supplement_keywords.csv`
2. **Edit the CSV file**:

   - To add a new keyword: Add a new row with keyword, category, auto_variations, exceptions, notes
   - To modify category grouping: Change the 'category' value
   - To add exceptions: Add comma-separated exception words

**Example 1 - Adding a new keyword "magazine" to books_media category:**

Add this row:

| keyword  | category    | auto_variations | exceptions | notes                     |
| -------- | ----------- | --------------- | ---------- | ------------------------- |
| magazine | books_media | yes             |            | Magazines and periodicals |

The LLM will now see:

```
Books Media: "book", "dvd", "magazine"
```

**Example 2 - Adding "protein bar" with exceptions:**

Add this row:

| keyword     | category | auto_variations | exceptions           | notes                                      |
| ----------- | -------- | --------------- | -------------------- | ------------------------------------------ |
| protein bar | food     | no              | supplement,nutrition | Keep if marked as supplement/nutrition bar |

**Explanation:**

- **Keyword**: "protein bar"
- **Category**: food (groups with other food items)
- **Auto variations**: no (exact match only, don't generate "protein bars")
- **Exceptions**: "supplement,nutrition" (if title has these words, DON'T filter)
- **Result**: "Chocolate Protein Bar" → filtered, but "Protein Bar Nutrition Supplement" → passes

**Example 3 - Modifying existing keyword's category:**

Before:

| keyword       | category     | auto_variations | exceptions                 | notes                   |
| ------------- | ------------ | --------------- | -------------------------- | ----------------------- |
| essential oil | topical_oils | yes             | supplement,capsule,softgel | Keep if supplement form |

After (changing category name):

| keyword       | category          | auto_variations | exceptions                 | notes                   |
| ------------- | ----------------- | --------------- | -------------------------- | ----------------------- |
| essential oil | oils_and_topicals | yes             | supplement,capsule,softgel | Keep if supplement form |

The LLM will now see it under "Oils And Topicals" instead of "Topical Oils"

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process a small batch to verify the keywords work as expected
5. Next processing run will automatically use the updated keywords

**File 2: `reference_data/safety_check_instructions.json`** (instructions and examples)

- Contains the safety check instructions template
- Includes hard-coded examples:
  - ✅ Items that ARE supplements (sports drinks, protein shakes, etc.)
  - ❌ Items that are NOT supplements (food, personal care, books, etc.)
- To change examples or instructions: Edit this file

**How It Works Internally:**

1. Load safety check template from `safety_check_instructions.json` (has placeholder `{non_supplement_keywords}`)
2. Load and format keywords from CSV by category
3. Replace placeholder with formatted keywords
4. Final prompt sent to OpenAI

### 2.2 Age Extraction (Step 1 in LLM)

The LLM extracts the target age group from the product title.

**What it does:**

- Searches the product title for age-related keywords
- Assigns the corresponding age group value
- If no keyword found, returns "AGE GROUP - NON SPECIFIC" (default)

**Reference File:** `reference_data/age_extraction_rules.json`

**Fields used by the system:**

- `instructions` - Instructions sent to the LLM
- `default` - Default value if no keyword found
- `keywords` - Keyword-to-value mappings

**Fields for documentation only:**

- `important_notes` - Not sent to LLM, for human reference
- `business_rule_context` - Not sent to LLM, explains downstream impact

**File Structure:**

```json
{
  "instructions": "Search title for age keywords...",
  "default": "AGE GROUP - NON SPECIFIC",
  "keywords": {
    "AGE GROUP - CHILD": ["kids", "children", "child", "pediatric", "kid's", "toddler"],
    "AGE GROUP - BABY": ["infant", "baby", "newborn"],
    "AGE GROUP - TEEN": ["teen", "teenager", "adolescent"],
    "AGE GROUP - ADULT": ["adult", "adults", "prenatal", "pregnancy", "pregnant", "postnatal", "postpartum"],
    "AGE GROUP - MATURE ADULT": ["mature adult", "50+", "60+", "50 plus", "senior"]
  }
}
```

**Valid Output Values:**

- `AGE GROUP - CHILD`
- `AGE GROUP - BABY`
- `AGE GROUP - TEEN`
- `AGE GROUP - ADULT` (includes prenatal/pregnancy products)
- `AGE GROUP - MATURE ADULT`
- `AGE GROUP - NON SPECIFIC` (default)

**Examples:**

| Product Title                            | Extracted Age            | Reasoning                             |
| ---------------------------------------- | ------------------------ | ------------------------------------- |
| Kids Chewable Multivitamin Gummies 120ct | AGE GROUP - CHILD        | Contains "kids"                       |
| Women's 50+ Multivitamin Tablets         | AGE GROUP - MATURE ADULT | Contains "50+"                        |
| Prenatal DHA Omega-3 Softgels            | AGE GROUP - ADULT        | Contains "prenatal" (coded as ADULT)  |
| Adult Multivitamin Daily Formula         | AGE GROUP - ADULT        | Contains "adult"                      |
| Pregnancy Vitamin with Folate            | AGE GROUP - ADULT        | Contains "pregnancy" (coded as ADULT) |
| Vitamin D3 5000 IU Softgels              | AGE GROUP - NON SPECIFIC | No age keyword found                  |

**Important Notes:**

- The LLM ignores age keywords in brand names (e.g., "Baby's Only Organic" brand)
- The LLM ignores age keywords in ingredient names (e.g., "Elderberry" contains "elder" but NOT an age indicator)
- "ADULT" and "NON SPECIFIC" are different and affect business rules differently
- **Prenatal/pregnancy/postnatal products are coded as AGE GROUP - ADULT** (matching original R system behavior)

**How to Modify:**

To add or change age keywords:

1. **Download the file** from S3: `reference_data/age_extraction_rules.json`
2. **Edit the JSON file**:

   - To add a new keyword: Add it to the appropriate age group array
   - To add a new age group: Create a new key with keyword array
   - To change default: Modify the "default" value

**Example - Adding "elderly" keyword to MATURE ADULT:**

Before:

```json
"AGE GROUP - MATURE ADULT": ["mature adult", "50+", "60+", "50 plus", "senior"]
```

After:

```json
"AGE GROUP - MATURE ADULT": ["mature adult", "50+", "60+", "50 plus", "senior", "elderly", "65+"]
```

**Example - Adding "youth" keyword to CHILD:**

Before:

```json
"AGE GROUP - CHILD": ["kids", "children", "child", "pediatric", "kid's", "toddler"]
```

After:

```json
"AGE GROUP - CHILD": ["kids", "children", "child", "pediatric", "kid's", "toddler", "youth"]
```

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process a small batch to verify the new keywords work correctly
5. Next processing run will automatically use the updated keywords

---

### 2.3 Gender Extraction (Step 2 in LLM)

The LLM extracts the target gender from the product title.

**What it does:**

- Searches the product title for gender-related keywords
- Assigns the corresponding gender value
- If no keyword found, returns "GENDER - NON SPECIFIC" (default)

**Reference File:** `reference_data/gender_extraction_rules.json`

**Fields used by the system:**

- `instructions` - Instructions sent to the LLM
- `default` - Default value if no keyword found
- `keywords` - Keyword-to-value mappings
- `special_rules` - Additional rules sent to the LLM

**File Structure:**

```json
{
  "instructions": "Search title for gender keywords...",
  "default": "GENDER - NON SPECIFIC",
  "keywords": {
    "GENDER - MALE": ["men", "men's", "male", "mens", "prostate"],
    "GENDER - FEMALE": ["women", "women's", "female", "womens", "prenatal", "pregnancy", "pregnant", "menopause", "menstrual"]
  },
  "special_rules": [
    "Products containing 'prostate' are male-specific",
    "Products containing 'prenatal', 'pregnancy', or 'menopause' are female-specific",
    "IGNORE gender keywords from brand names (e.g., 'Women's Best' is a brand)"
  ]
}
```

**Valid Output Values:**

- `GENDER - MALE`
- `GENDER - FEMALE`
- `GENDER - NON SPECIFIC` (default)

**Examples:**

| Product Title                        | Extracted Gender      | Reasoning                             |
| ------------------------------------ | --------------------- | ------------------------------------- |
| Men's Daily Multivitamin 60 Tablets  | GENDER - MALE         | Contains "men's"                      |
| Women's 50+ Multivitamin             | GENDER - FEMALE       | Contains "women's"                    |
| Prostate Support Formula 90 Capsules | GENDER - MALE         | Contains "prostate" (male-specific)   |
| Prenatal DHA Omega-3 Softgels        | GENDER - FEMALE       | Contains "prenatal" (female-specific) |
| Vitamin D3 5000 IU Softgels          | GENDER - NON SPECIFIC | No gender keyword found               |

**Important Notes:**

- The LLM ignores gender keywords in brand names (e.g., "Women's Best" brand)
- Special keywords like "prostate", "prenatal", "pregnancy", "menopause" automatically indicate gender
- "MALE" and "NON SPECIFIC" are different and affect business rules differently (e.g., multivitamin subcategory assignment)

**How to Modify:**

To add or change gender keywords:

1. **Download the file** from S3: `reference_data/gender_extraction_rules.json`
2. **Edit the JSON file**:

   - To add a new keyword: Add it to the appropriate gender array
   - To change default: Modify the "default" value
   - To add special rules: Add to the "special_rules" array

**Example - Adding "gentleman" keyword to MALE:**

Before:

```json
"GENDER - MALE": ["men", "men's", "male", "mens", "prostate"]
```

After:

```json
"GENDER - MALE": ["men", "men's", "male", "mens", "prostate", "gentleman"]
```

**Example - Adding "ladies" keyword to FEMALE:**

Before:

```json
"GENDER - FEMALE": ["women", "women's", "female", "womens", "prenatal", "pregnancy", "pregnant", "menopause", "menstrual"]
```

After:

```json
"GENDER - FEMALE": ["women", "women's", "female", "womens", "prenatal", "pregnancy", "pregnant", "menopause", "menstrual", "ladies"]
```

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process a small batch to verify the new keywords work correctly
5. Next processing run will automatically use the updated keywords

---

### 2.4 Form Extraction (Step 3 in LLM)

The LLM extracts the physical form of the supplement from the product title.

**What it does:**

- Searches the product title for form-related keywords
- Assigns the most specific form value possible
- If multiple forms detected, applies priority rules to resolve conflicts
- If no keyword found, returns "OTHER/UNKNOWN" (default)

**Reference File 1:** `reference_data/form_extraction_rules.json`

**Fields used by the system:**

- `instructions` - Instructions sent to the LLM
- `default` - Default value if no keyword found
- `keywords` - Keyword-to-value mappings for all form types

**File Structure:**

```json
{
  "instructions": "Search title for form keywords. Extract the physical form...",
  "default": "OTHER/UNKNOWN",
  "keywords": {
    "CAPSULE": ["capsule", "capsules", "vcap", "vcaps", "cap", "caps"],
    "VEGETABLE CAPSULE": ["vegetable capsule", "veg capsule", "vegan capsules", "vcaps"],
    "TABLET": ["tablet", "tablets", "tab", "tabs"],
    "SOFTGEL": ["softgel", "softgels", "soft gel", "liquid gels", "gelcaps"],
    "POWDER": ["powder", "drinkmix", "drink mix"],
    "LIQUID": ["liquid", "drink", "shake", "syrup"],
    "GUMMY": ["gummy", "gummies", "gummi"],
    "DROPS": ["drops", "drop"],
    "LOZENGE": ["lozenge", "lozenges", "throat drop", "cough drop"],
    "BAR": ["bar", "bars"],
    "SPRAY": ["spray", "nasal spray", "throat spray", "mist"]
  }
}
```

**Reference File 2:** `reference_data/form_priority_rules.json`

**Fields used by the system:**

- `rules` - Array of priority rules with condition, action, and reason

**Fields for documentation only:**

- `title`, `description`, `client_instructions` - Not sent to LLM

**File Structure:**

```json
{
  "title": "Form Priority and Conflict Resolution Rules",
  "description": "Handle cases where multiple form keywords appear...",
  "rules": [
    {
      "rule_id": "FORM-RULE-01",
      "priority": 1,
      "description": "Cough drops or throat drops are always lozenges",
      "condition": "If title contains 'cough drop' OR 'throat drop'",
      "action": "Set form to LOZENGE",
      "reason": "These terms always indicate lozenge form"
    },
    {
      "rule_id": "FORM-RULE-02",
      "priority": 2,
      "description": "Powder IN capsules means capsule form, not powder",
      "condition": "If title contains BOTH 'powder' AND 'capsule'",
      "action": "Set form to CAPSULE (not POWDER)",
      "reason": "Powder describes ingredient state, capsule is delivery form"
    }
  ],
  "client_instructions": "To add a new rule, add an entry with the next rule_id..."
}
```

**Valid Output Values:**

- `CAPSULE`, `VEGETABLE CAPSULE`, `TABLET`, `CAPLET`, `CHEWABLE TABLET`
- `SOFTGEL`, `SOFT CHEW`, `POWDER`, `LIQUID`, `GUMMY`, `DROPS`
- `LOZENGE`, `BAR`, `SPRAY`, `TOPICAL GELS & CREAMS`, `PELLET`
- `TINCTURE`, `GUM`, `SUPPOSITORIES`
- `OTHER/UNKNOWN` (default)

**Examples:**

| Product Title                         | Extracted Form    | Reasoning                                   |
| ------------------------------------- | ----------------- | ------------------------------------------- |
| Vitamin D3 5000 IU Softgels 100 Count | SOFTGEL           | Contains "softgels"                         |
| Turmeric Powder in Vegetable Capsules | VEGETABLE CAPSULE | Priority rule: powder IN capsules = capsule |
| Kids Chewable Multivitamin Gummies    | GUMMY             | Contains "gummies"                          |
| Elderberry Cough Drops 30 Count       | LOZENGE           | Priority rule: cough drops = lozenge        |
| Protein Powder Chocolate 2lb          | POWDER            | Contains "powder"                           |

**Priority Rules (from form_priority_rules.json):**

When multiple form keywords are found or specific combinations appear, these 5 rules determine the final form. They are checked in priority order (1 is highest priority):

**Rule 1 (FORM-RULE-01): Cough/Throat Drops → LOZENGE**

- **When:** Title contains "cough drop" OR "throat drop"
- **Result:** Set form to LOZENGE
- **Why:** These terms always indicate lozenge form, regardless of other keywords
- **Example:** "Elderberry Cough Drops 30 Count" → LOZENGE

**Rule 2 (FORM-RULE-02): Powder IN Capsules → CAPSULE**

- **When:** Title contains BOTH "powder" AND "capsule"
- **Result:** Set form to CAPSULE (not POWDER)
- **Why:** Powder describes the ingredient state, capsule is the actual delivery form
- **Example:** "Turmeric Powder in Vegetable Capsules" → CAPSULE (or VEGETABLE CAPSULE if specified)

**Rule 3 (FORM-RULE-03): Vegetable Capsule → VEGETABLE CAPSULE**

- **When:** Title contains "vegetable capsule", "veg capsule", "vegan capsule" or similar variants
- **Result:** Set form to VEGETABLE CAPSULE (not just CAPSULE)
- **Why:** Be specific when the product explicitly mentions vegetable/vegan/vegetarian capsules
- **Example:** "Vitamin D3 in Vegan Capsules" → VEGETABLE CAPSULE

**Rule 4 (FORM-RULE-04): Gel/Liquid Capsules → SOFTGEL**

- **When:** Title contains "gel capsule" OR "liquid capsule"
- **Result:** Set form to SOFTGEL (not CAPSULE)
- **Why:** These terms specifically indicate softgel form, not hard capsules
- **Example:** "Omega-3 Liquid Capsules" → SOFTGEL

**Rule 5 (FORM-RULE-05): Chewable Tablet → CHEWABLE TABLET**

- **When:** Title contains "chew tablet" OR "chewable tablet"
- **Result:** Set form to CHEWABLE TABLET (not TABLET)
- **Why:** Distinguish chewable from regular swallow tablets
- **Example:** "Vitamin C Chewable Tablets" → CHEWABLE TABLET

**How to Modify File 1 (form_extraction_rules.json):**

To add or change form keywords:

1. **Download the file** from S3: `reference_data/form_extraction_rules.json`
2. **Edit the JSON file** to add keywords to existing forms or create new forms

**Example 1 - Adding "gel cap" keyword to SOFTGEL:**

Before:

```json
"SOFTGEL": ["softgel", "softgels", "soft gel", "liquid gels", "gelcaps"]
```

After:

```json
"SOFTGEL": ["softgel", "softgels", "soft gel", "liquid gels", "gelcaps", "gel cap", "gel caps"]
```

**Example 2 - Creating a new form type "WAFER":**

Add this to the keywords object:

```json
"WAFER": ["wafer", "wafers", "edible film", "thin strip", "dissolvable strip"]
```

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process a small batch
5. Next processing run will use the new keywords

---

**How to Modify File 2 (form_priority_rules.json):**

To add or change priority rules:

1. **Download the file** from S3: `reference_data/form_priority_rules.json`
2. **Add a new rule** to the "rules" array with the next rule_id (FORM-RULE-06, etc.)

**Example - Adding a rule for "extract in tablet":**

Add this to the rules array:

```json
{
  "rule_id": "FORM-RULE-06",
  "priority": 6,
  "description": "Extract in tablet means tablet form",
  "condition": "If title contains BOTH 'extract' AND 'tablet'",
  "action": "Set form to TABLET (not LIQUID)",
  "reason": "Extract describes ingredient preparation, tablet is the delivery form"
}
```

**Structure explanation:**

- `rule_id` - Unique ID (increment from last rule)
- `priority` - Execution order (lower number = higher priority)
- `description` - Brief summary
- `condition` - When to apply this rule
- `action` - What to do when condition is met
- `reason` - Why this rule exists

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process a small batch with products matching your rule
5. Next processing run will use the new rule

---

### 2.5 Organic Extraction (Step 4 in LLM)

**What It Does:**

The LLM checks if the product is organic by scanning the title for organic-related keywords. It uses a priority-based system to handle edge cases where both "organic" and "inorganic" appear in the same title.

**Reference File:** `reference_data/organic_extraction_rules.json`

**File Structure:**

```json
{
  "priority_order": [
    {
      "priority": 1,
      "keywords": ["inorganic"],
      "result": "NOT ORGANIC",
      "reason": "If 'inorganic' is mentioned, the product is NOT organic"
    },
    {
      "priority": 2,
      "keywords": ["organic", "usda organic", "certified organic"],
      "result": "ORGANIC",
      "reason": "If 'organic' is mentioned (and no 'inorganic'), the product is organic"
    }
  ],
  "default": "NOT ORGANIC",
  "instructions": "Check title for organic keywords using PRIORITY ORDER...",
  "edge_case_example": "Title: 'Supplement with organic and inorganic minerals' → Result: NOT ORGANIC"
}
```

**Fields Used by the System:**

- `priority_order` - Array of rules checked in order (priority 1 checked first)
  - `priority` - Execution order (1 = highest priority)
  - `keywords` - Array of keywords to search for
  - `result` - Value to return if keyword found
  - `reason` - Explanation for the LLM
- `default` - Value to return if no keywords found
- `instructions` - How the LLM should process this step
- `edge_case_example` - Example of complex scenario

**Valid Output Values:**

- `"ORGANIC"` - Product is organic
- `"NOT ORGANIC"` - Product is not organic (default)

**How It Works:**

1. LLM checks title for "inorganic" keyword first (Priority 1)
   - If found → Returns "NOT ORGANIC" immediately
2. If no "inorganic", checks for "organic" keywords (Priority 2)
   - If found → Returns "ORGANIC"
3. If neither found → Returns default "NOT ORGANIC"

**Examples:**

| Product Title                                    | Keywords Found                      | Result      | Reasoning                                    |
| ------------------------------------------------ | ----------------------------------- | ----------- | -------------------------------------------- |
| "Nature Made Organic Turmeric 500mg"             | "organic"                           | ORGANIC     | Contains organic keyword                     |
| "Garden of Life Vitamin D3 60 Capsules"          | none                                | NOT ORGANIC | No organic keywords (default)                |
| "Supplement with organic and inorganic minerals" | "organic", "inorganic"              | NOT ORGANIC | Priority 1 rule (inorganic) takes precedence |
| "USDA Certified Organic Ashwagandha"             | "usda organic", "certified organic" | ORGANIC     | Contains organic certification keywords      |

**How to Modify:**

To change organic detection behavior:

1. **Download the file** from S3: `reference_data/organic_extraction_rules.json`
2. **Edit the JSON file**:

   - To add new organic keywords: Add to priority 2 keywords array
   - To add new non-organic keywords: Add to priority 1 keywords array
   - To change default: Modify "default" value
   - To change priority order: Adjust "priority" numbers (lower = higher priority)

**Example - Adding "non-gmo organic" keyword:**

Before:

```json
{
  "priority": 2,
  "keywords": ["organic", "usda organic", "certified organic"],
  "result": "ORGANIC",
  "reason": "If 'organic' is mentioned (and no 'inorganic'), the product is organic"
}
```

After:

```json
{
  "priority": 2,
  "keywords": ["organic", "usda organic", "certified organic", "non-gmo organic"],
  "result": "ORGANIC",
  "reason": "If 'organic' is mentioned (and no 'inorganic'), the product is organic"
}
```

**Example - Adding "synthetic" as non-organic keyword:**

Add this to the priority_order array (as priority 1 alongside "inorganic"):

Before:

```json
{
  "priority": 1,
  "keywords": ["inorganic"],
  "result": "NOT ORGANIC",
  "reason": "If 'inorganic' is mentioned, the product is NOT organic"
}
```

After:

```json
{
  "priority": 1,
  "keywords": ["inorganic", "synthetic"],
  "result": "NOT ORGANIC",
  "reason": "If 'inorganic' or 'synthetic' is mentioned, the product is NOT organic"
}
```

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process products with organic/non-organic keywords
5. Next processing run will use the updated rules

---

### 2.6 Pack Count Extraction (Step 5 in LLM)

**What It Does:**

The LLM extracts the SIZE (quantity) from the product title. This represents how much of the product you get, such as:

- Discrete units: "60 capsules" → size = 60
- Volume: "8 fl oz" → size = 8
- Weight: "2 lbs" → size = 2

**⚠️ CRITICAL:** Size is NOT the same as dosage (mg, IU, mcg). The LLM must distinguish between these.

**Reference File:** `reference_data/size_extraction_rules.json`

**File Structure:**

```json
{
  "description": "Rules for extracting SIZE (quantity) from product title",
  "instructions": "Extract the QUANTITY (size number) from the title...",
  "keywords": {
    "size_indicators": [
      "capsules", "capsule", "caps", "cap", "vcaps", "vegcaps",
      "tablets", "tablet", "tabs", "tab",
      "softgels", "softgel", "gels", "gel",
      "gummies", "gummy", "pills", "pill",
      "servings", "serving", "doses", "dose",
      "pieces", "piece", "lozenges", "lozenge", "drops",
      "count", "ct", "ea", "each"
    ],
    "volume_indicators": ["oz", "fl oz", "fluid oz", "ounces", "ounce"],
    "weight_indicators": [
      "lb", "lbs", "pound", "pounds",
      "kg", "kgs", "kilos", "kilogram", "kilograms",
      "g", "gm", "gram", "grams",
      "mg", "milligram", "milligrams",
      "ml", "milliliter", "milliliters", "millil"
    ]
  },
  "default": "UNKNOWN",
  "examples": [ /* see examples below */ ],
  "warnings": [ /* critical warnings about dosage vs size confusion */ ]
}
```

**Fields Used by the System:**

- `instructions` - Instructions sent to the LLM
- `keywords` - Three categories of size indicators:
  - `size_indicators` - For discrete units (capsules, tablets, etc.)
  - `volume_indicators` - For liquid volumes (oz, fl oz, etc.)
  - `weight_indicators` - For weight measurements (lbs, g, kg, etc.)
- `default` - Value if no size found ("UNKNOWN")
- `examples` - Example extractions for the LLM
- `warnings` - Critical rules about dosage vs size confusion

**Fields for documentation only:**

- `description` - Not sent to LLM

**Valid Output Values:**

- Any numeric value (as a string): `"60"`, `"180"`, `"2"`, `"500"`, etc.
- `"UNKNOWN"` - Default when no size information found

**How It Works:**

1. LLM scans title for numbers followed by size indicator keywords
2. Identifies which type of size:
   - **Discrete units:** "60 capsules" → Extract 60
   - **Volume:** "8 fl oz" → Extract 8
   - **Weight:** "2 lbs" or "500 g" → Extract the number
3. Ignores dosage numbers (mg, IU, mcg)
4. Returns the size number or "UNKNOWN"

**Examples:**

| Product Title                   | Size Extracted | Reasoning                                                |
| ------------------------------- | -------------- | -------------------------------------------------------- |
| "Fish Oil 1000mg 180 Softgels"  | 180            | Found "180 softgels" (NOT 1000, which is dosage)         |
| "Vitamin D 5000 IU 60 Capsules" | 60             | Found "60 capsules" (NOT 5000, which is dosage in IU)    |
| "Elderberry Syrup 8 fl oz"      | 8              | Found "8 fl oz" (volume measurement)                     |
| "Whey Protein Powder 2 lbs"     | 2              | Found "2 lbs" (weight measurement)                       |
| "Creatine Monohydrate 500 g"    | 500            | Found "500 g" (weight in grams)                          |
| "CoQ10 100mg 60 Capsules"       | 60             | Size is 60 (NOT 100, which is dosage, NOT 10 from CoQ10) |
| "Multivitamin Gummy"            | UNKNOWN        | No size information found in title                       |

**⚠️ Critical Warnings (from the file):**

The LLM is instructed with these critical rules:

1. **Do NOT confuse dosage numbers (mg, mcg, IU, mcg/ml) with size**
2. **Look for the number that comes BEFORE unit keywords** (capsules, tablets, softgels, oz, lbs, g, kg)
3. **For weight/volume products** (powder, liquid), EXTRACT the weight/volume number as size
4. **If multiple numbers exist**, choose the one associated with units, NOT dosage

**How to Modify:**

To change size extraction behavior:

1. **Download the file** from S3: `reference_data/size_extraction_rules.json`
2. **Edit the JSON file**:

   - To add new size keywords: Add to the appropriate array (`size_indicators`, `volume_indicators`, or `weight_indicators`)
   - To add new examples: Add to the `examples` array
   - To add new warnings: Add to the `warnings` array
   - To change default: Modify `default` value

**Example 1 - Adding "pouches" as a size indicator:**

Before:

```json
"size_indicators": [
  "capsules", "capsule", "caps", "cap", "vcaps", "vegcaps",
  "tablets", "tablet", "tabs", "tab",
  "softgels", "softgel", "gels", "gel",
  "gummies", "gummy", "pills", "pill",
  "servings", "serving", "doses", "dose",
  "pieces", "piece", "lozenges", "lozenge", "drops",
  "count", "ct", "ea", "each"
]
```

After:

```json
"size_indicators": [
  "capsules", "capsule", "caps", "cap", "vcaps", "vegcaps",
  "tablets", "tablet", "tabs", "tab",
  "softgels", "softgel", "gels", "gel",
  "gummies", "gummy", "pills", "pill",
  "servings", "serving", "doses", "dose",
  "pieces", "piece", "lozenges", "lozenge", "drops",
  "count", "ct", "ea", "each",
  "pouches", "pouch", "packets", "packet"
]
```

**Example 2 - Adding a new example to help the LLM:**

Add this to the `examples` array:

```json
{
  "title": "Magnesium Glycinate 400mg 120 Tablets",
  "size": "120",
  "reasoning": "Found '120 tablets' - the size is 120 (not 400, which is dosage in mg)"
}
```

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process products with the new size indicators
5. Next processing run will use the updated keywords

---

### 2.7 Unit Extraction (Step 6 in LLM)

**What It Does:**

The LLM identifies the unit of measurement for the size value extracted in the previous step. It standardizes different unit variations to a base form (e.g., "capsules", "caps", "vcaps" → "COUNT").

**Reference File:** `reference_data/unit_extraction_rules.json`

**File Structure:**

```json
{
  "description": "Rules for extracting Unit of Measurement from product title",
  "instructions": "Identify the unit type from the product title. Return the standardized unit form.",
  "unit_types": {
    "discrete_units": {
      "description": "Discrete countable units - return 'COUNT'",
      "indicators": ["capsules", "capsule", "caps", "cap", "tablets", "tablet", "softgels", "gummies", ...],
      "output": "COUNT"
    },
    "volume_units": {
      "description": "Volume units",
      "indicators": ["oz", "fl oz", "fluid oz", "ounce", "ounces", "fluid ounce"],
      "output": "OZ"
    },
    "weight_units": {
      "description": "Weight units",
      "indicators": {
        "lb": ["lb", "lbs", "pound", "pounds"],
        "kg": ["kg", "kgs", "kilos", "kilogram", "kilograms"],
        "g": ["g", "gm", "gram", "grams"],
        "mg": ["mg", "milligram", "milligrams"],
        "ml": ["ml", "milliliter", "milliliters", "millil"]
      }
    }
  },
  "default": "UNKNOWN",
  "rules": [ /* standardization rules */ ],
  "examples": [ /* see examples below */ ],
  "conversion_factors_for_python": { /* used by Python code, not LLM */ }
}
```

**Fields Used by the System:**

- `instructions` - Instructions sent to the LLM
- `unit_types` - Three categories of units:
  - `discrete_units` - For countable items → Returns "COUNT"
  - `volume_units` - For liquid volumes → Returns "oz"
  - `weight_units` - For weight measurements → Returns base form (lb, kg, g, mg, ml)
- `default` - Value if no unit found ("UNKNOWN")
- `rules` - Standardization rules for the LLM
- `examples` - Example extractions for the LLM

**Fields for documentation only:**

- `description` - Not sent to LLM
- `conversion_factors_for_python` - Used by Python post-processing code, NOT sent to LLM

**Valid Output Values:**

- `"COUNT"` - For discrete units (capsules, tablets, softgels, gummies, etc.)
- `"oz"` - For volume units (fl oz, ounces, etc.)
- `"lb"` - For pounds
- `"kg"` - For kilograms
- `"g"` - For grams
- `"mg"` - For milligrams
- `"ml"` - For milliliters
- `"UNKNOWN"` - Default when no unit found

**How It Works:**

1. LLM identifies which type of unit is present in the title
2. Applies standardization rules:
   - **Discrete units** (capsules, tablets, softgels, gummies, pills, servings, lozenges, drops, count, pieces) → Return "COUNT"
   - **Volume units** (oz, fl oz, fluid oz, ounce, ounces) → Return "oz"
   - **Weight units** (lbs, pounds, kg, grams, etc.) → Return base form (lb, kg, g, mg, ml)
3. Returns the standardized unit or "UNKNOWN"

**Examples:**

| Product Title                  | Unit Extracted | Reasoning                                        |
| ------------------------------ | -------------- | ------------------------------------------------ |
| "Fish Oil 1000mg 180 Softgels" | COUNT          | Discrete units "softgels" found → return COUNT  |
| "Vitamin D 60 Capsules"        | COUNT          | Discrete units "capsules" found → return COUNT  |
| "Elderberry Syrup 8 fl oz"     | oz             | Volume unit "fl oz" found → return "oz"         |
| "Whey Protein Powder 2 lbs"    | lb             | Weight unit "lbs" found → return base form "lb" |
| "Creatine Monohydrate 500 g"   | g              | Weight unit "g" found → return "g"              |
| "Vitamin C Powder 1 kg"        | kg             | Weight unit "kg" found → return "kg"            |
| "Multivitamin Gummy"           | UNKNOWN        | No unit found → return UNKNOWN                  |

**Standardization Rules (from the file):**

1. **Discrete units** (capsules, tablets, softgels, etc.) → return "COUNT"
2. **Volume units** (oz, fl oz) → return "oz"
3. **Weight units** found (lbs, pounds, etc.) → return base form ("lb", "kg", "g", "mg", "ml")
4. **No unit found** → return "UNKNOWN"

---

**⚙️ Post-Processing Note:**

After the LLM extracts size and unit, **Step 3: Post-Processing** automatically converts weight units to OZ for standardization:

- `lb`, `kg`, `g`, `mg`, `ml` → Converted to `OZ` using conversion factors
- `COUNT` and `oz` → No conversion needed

The `conversion_factors_for_python` field in this JSON file provides the conversion factors used by Python post-processing code (NOT used by the LLM).

**Example:** LLM extracts size="2", unit="lb" → Step 3 converts to size="32", unit="OZ"

*See **Step 3: Post-Processing** section for detailed conversion logic and examples.*

---

**How to Modify:**

To change unit extraction behavior:

1. **Download the file** from S3: `reference_data/unit_extraction_rules.json`
2. **Edit the JSON file**:

   - To add new discrete unit keywords: Add to `unit_types.discrete_units.indicators` array
   - To add new volume unit keywords: Add to `unit_types.volume_units.indicators` array
   - To add new weight units: Add to `unit_types.weight_units.indicators` object
   - To add new examples: Add to the `examples` array
   - To change default: Modify `default` value

**Example 1 - Adding "pouches" and "packets" as discrete units:**

Before:

```json
"discrete_units": {
  "description": "Discrete countable units - return 'COUNT'",
  "indicators": [
    "capsules", "capsule", "caps", "cap",
    "tablets", "tablet", "tabs", "tab",
    "softgels", "softgel", "gels",
    "gummies", "gummy", "pills", "pill",
    "servings", "serving", "lozenges", "lozenge",
    "drops", "count", "ct", "ea", "each", "pieces", "piece"
  ],
  "output": "COUNT"
}
```

After:

```json
"discrete_units": {
  "description": "Discrete countable units - return 'COUNT'",
  "indicators": [
    "capsules", "capsule", "caps", "cap",
    "tablets", "tablet", "tabs", "tab",
    "softgels", "softgel", "gels",
    "gummies", "gummy", "pills", "pill",
    "servings", "serving", "lozenges", "lozenge",
    "drops", "count", "ct", "ea", "each", "pieces", "piece",
    "pouches", "pouch", "packets", "packet", "sachets", "sachet"
  ],
  "output": "COUNT"
}
```

**Example 2 - Adding "liters" to volume units:**

Before:

```json
"volume_units": {
  "description": "Volume units",
  "indicators": ["oz", "fl oz", "fluid oz", "ounce", "ounces", "fluid ounce"],
  "output": "OZ"
}
```

After:

```json
"volume_units": {
  "description": "Volume units",
  "indicators": ["oz", "fl oz", "fluid oz", "ounce", "ounces", "fluid ounce", "liter", "liters", "l"],
  "output": "OZ"
}
```

**Note:** If you change volume units to include liters, you may need to update the output to a more generic unit like "VOLUME" or keep converting to "oz".

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process products with the new unit keywords
5. Next processing run will use the updated keywords

---

### 2.8 Size Extraction (Step 7 in LLM)

**What It Does:**

The LLM extracts the pack count (number of packages or bottles in the product). This represents how many separate containers/bottles are included in one purchase.

**⚠️ CRITICAL:** Pack count is NOT the same as size. Pack count = number of bottles/packages, Size = quantity per bottle.

**Reference File:** `reference_data/pack_count_extraction_rules.json`

**File Structure:**

```json
{
  "description": "Rules for extracting Pack Count (number of packages/bottles in the product)",
  "instructions": "Extract the pack count if explicitly mentioned. Look for keywords like 'pack', 'bottles'...",
  "keywords": {
    "pack_indicators": [
      "pack", "packs", "pk", "pks",
      "package", "packages",
      "bottle", "bottles",
      "pack of", "case of"
    ]
  },
  "default": 1,
  "default_reasoning": "No pack keywords found, default to 1",
  "patterns": [
    {
      "pattern": "[NUMBER] pack/packs/bottles",
      "examples": ["2 pack", "3 bottles", "4 packs"]
    },
    {
      "pattern": "pack of [NUMBER] / case of [NUMBER]",
      "examples": ["pack of 2", "case of 6"]
    }
  ],
  "examples": [ /* see examples below */ ],
  "warnings": [ /* critical warnings */ ]
}
```

**Fields Used by the System:**

- `instructions` - Instructions sent to the LLM
- `keywords.pack_indicators` - Keywords that indicate pack count
- `default` - Default value if no pack keywords found (1)
- `default_reasoning` - Why default is 1
- `patterns` - Common patterns to look for
- `examples` - Example extractions for the LLM
- `warnings` - Critical rules about pack count vs size

**Fields for documentation only:**

- `description` - Not sent to LLM

**Valid Output Values:**

- Any numeric value (as integer): `1`, `2`, `3`, `4`, `6`, etc.
- `1` (default) - If no pack keywords found

**How It Works:**

1. LLM scans title for pack indicator keywords
2. Looks for patterns:
   - **"[NUMBER] pack/packs/bottles"** → Extract the number
   - **"pack of [NUMBER]"** → Extract the number
   - **"case of [NUMBER]"** → Extract the number
3. If no pack keywords found → Returns 1 (single unit, default)

**Examples:**

| Product Title                  | Pack Count | Reasoning                               |
| ------------------------------ | ---------- | --------------------------------------- |
| "2 Pack Fish Oil 180 Capsules" | 2          | Found "2 pack" (NOT 180, which is size) |
| "Pack of 3 Vitamin D 5000 IU"  | 3          | Found "pack of 3"                       |
| "4 Bottles Vitamin C 500mg"    | 4          | Found "4 bottles"                       |
| "Multivitamin 60 Tablets"      | 1          | No pack keyword found → default to 1   |
| "Elderberry Syrup 8 fl oz"     | 1          | No pack keyword found → default to 1   |
| "Case of 6 Protein Bars"       | 6          | Found "case of 6"                       |

**⚠️ Critical Warnings (from the file):**

1. **Do NOT confuse size (capsules/tablets quantity) with pack count (bottles/packages)**
   - Example: "2 Pack Fish Oil 180 Capsules" → Pack Count = 2, Size = 180
2. **If no pack keywords found, default to 1** (single unit/bottle)

**Common Patterns:**

1. **"[NUMBER] pack"** → "2 pack", "3 packs", "4 pk"
2. **"pack of [NUMBER]"** → "pack of 2", "pack of 3"
3. **"case of [NUMBER]"** → "case of 6", "case of 12"
4. **"[NUMBER] bottles"** → "2 bottles", "3 bottles"

**How to Modify:**

To change pack count extraction behavior:

1. **Download the file** from S3: `reference_data/pack_count_extraction_rules.json`
2. **Edit the JSON file**:

   - To add new pack keywords: Add to `keywords.pack_indicators` array
   - To add new patterns: Add to `patterns` array
   - To add new examples: Add to `examples` array
   - To change default: Modify `default` value

**Example 1 - Adding "bundle" and "twin pack" keywords:**

Before:

```json
"pack_indicators": [
  "pack", "packs", "pk", "pks",
  "package", "packages",
  "bottle", "bottles",
  "pack of", "case of"
]
```

After:

```json
"pack_indicators": [
  "pack", "packs", "pk", "pks",
  "package", "packages",
  "bottle", "bottles",
  "pack of", "case of",
  "bundle", "bundles",
  "twin pack", "twin-pack"
]
```

**Example 2 - Adding a new pattern:**

Add this to the `patterns` array:

```json
{
  "pattern": "[NUMBER]-pack",
  "examples": ["2-pack", "3-pack", "twin-pack"]
}
```

**Example 3 - Adding a new example to help the LLM:**

Add this to the `examples` array:

```json
{
  "title": "Bundle of 2 Probiotic Supplements 60 Capsules Each",
  "pack_count": 2,
  "reasoning": "Found 'bundle of 2' - pack count is 2 (NOT 60, which is size per bottle)"
}
```

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process products with pack keywords
5. Next processing run will use the updated keywords

---

### 2.9 Ingredient Extraction (Step 8 in LLM)

**What It Does:**

The LLM extracts ALL functional ingredients from the product title and for EACH ingredient, calls the `lookup_ingredient()` tool to get its category and subcategory from the database. This is the MOST IMPORTANT step for determining the product's final category/subcategory.

**⚠️ CRITICAL:**

- Extract ALL ingredients, not just the primary one
- For EACH ingredient, call `lookup_ingredient()` tool
- Track each ingredient's POSITION in the title (important for determining primary ingredient)
- Use the NORMALIZED NAME from the lookup result, not your raw extraction

**Reference Files:**

1. `reference_data/ingredient_extraction_rules.json` - Extraction rules and instructions
2. `reference_data/ingredient_category_lookup.csv` - Database used by `lookup_ingredient()` tool

**File Structure (ingredient_extraction_rules.json):**

```json
{
  "instructions": "Extract ALL functional ingredients from the product title. For each ingredient found, record its NAME and POSITION...",
  "extraction_steps": [
    "1. Scan the entire title for ingredient names",
    "2. For EACH ingredient found, record: ingredient_name and position",
    "3. Return ALL ingredients found, not just the first one",
    "4. For each ingredient, you MUST call the lookup_ingredient() tool"
  ],
  "critical_rules": [
    "DO NOT split compound ingredient names into separate ingredients",
    "Example: 'Vitamin D3' → Extract as ONE ingredient 'vitamin d3' (NOT 'vitamin d' + 'd3')",
    ...
  ],
  "exclusions": {
    "description": "Keywords that should NOT be extracted as functional ingredients...",
    "flavor_keywords": ["cherry", "acai", "cranberry", "blueberry", "vanilla", "chocolate", ...],
    "instructions": [ /* context clues for flavors vs ingredients */ ],
    "examples": [ /* see below */ ]
  },
  "special_cases": {
    "multivitamin": { /* keywords that trigger multivitamin logic */ },
    "protein": { /* keywords that trigger protein logic */ }
  },
  "tool_calling": {
    "tool_name": "lookup_ingredient",
    "parameters": { "ingredient_name": "..." },
    "correct_examples": [ /* see below */ ],
    "wrong_examples": [ /* see below */ ]
  },
  "special_handling": {
    "probiotics": { /* how to handle probiotic strains */ },
    "combo_products": { /* how to handle combo ingredients */ },
    "normalized_names": { /* CRITICAL: use normalized names from lookup */ },
    "combo_detection": { /* NEW: glucosamine+chondroitin, B vitamins, A+D combos */ },
    "context_dependent_ingredients": { /* NEW: angelica/dong quai, arnica, basil, coq10 */ }
  },
  "primary_ingredient_logic": {
    "rule": "PRIMARY ingredient is determined by POSITION in title (first found = primary)",
    "exception": "If 'Multiple Vitamin' is detected anywhere, it becomes PRIMARY regardless of position"
  },
  "output_format": { /* how to structure the JSON output */ }
}
```

**Fields Used by the System:**

- `instructions` - Main instructions sent to the LLM
- `extraction_steps` - 4-step process for extracting ingredients
- `critical_rules` - Rules about compound ingredient names (don't split "Vitamin D3", etc.)
- `exclusions` - Flavor keywords to skip (unless functional ingredients)
  - `flavor_keywords` - List of flavor descriptors
  - `instructions` - How to distinguish flavors from ingredients
  - `examples` - 5 examples showing when to extract vs skip
- `special_cases` - Multivitamin and protein keywords
- `tool_calling` - How to call `lookup_ingredient()` tool correctly
- `special_handling` - 5 advanced handlers:
  - `probiotics` - Probiotic strain fallback logic
  - `combo_products` - Try full phrase before splitting (e.g., "echinacea goldenseal")
  - `normalized_names` - Use normalized names from lookup results
  - **`combo_detection`** - ✨ NEW: Merge ingredient combos (glucosamine+chondroitin, B vitamins, A+D)
  - **`context_dependent_ingredients`** - ✨ NEW: Context-aware lookups (angelica/dong quai, arnica types, etc.)
- `primary_ingredient_logic` - How to determine which ingredient is primary
- `output_format` - Structure for JSON output with ingredients array

**Database File (ingredient_category_lookup.csv):**

The `lookup_ingredient()` tool queries this CSV database that contains ~900 ingredient mappings:

| Column             | Description                                                                          |
| ------------------ | ------------------------------------------------------------------------------------ |
| `INGREDIENT`     | Normalized ingredient name (e.g., "VITAMIN C (NOT ESTER-C)", "PROBIOTIC SUPPLEMENT") |
| `NW_CATEGORY`    | Nature's Way category assignment                                                     |
| `NW_SUBCATEGORY` | Nature's Way subcategory assignment                                                  |

**How It Works - The 4-Step Process:**

**Step 1: Scan for Ingredient Names**

- LLM reads the entire product title
- Identifies functional ingredient keywords
- Records each ingredient name found

**Step 2: Record Position for Each Ingredient**

- For each ingredient, notes its character position in title (0-indexed)
- Position is used later to determine primary ingredient
- First ingredient by position = primary (unless multivitamin override)

**Step 3: Call lookup_ingredient() Tool for EACH Ingredient**

- For every ingredient found, LLM must call: `lookup_ingredient(ingredient_name="[name]")`
- Tool queries the ingredient_category_lookup.csv database
- Returns: normalized name, category, subcategory, found status

**Step 4: Use Normalized Names in Output**

- ⚠️ CRITICAL: LLM must use the "ingredient" field from tool response, NOT its raw extraction
- Example: LLM extracts "vitamin c" → Tool returns "VITAMIN C (NOT ESTER-C)" → Use "VITAMIN C (NOT ESTER-C)" in output

**⚠️ Critical Rules (from the file):**

**Rule 1: Do NOT Split Compound Ingredient Names**

- ❌ WRONG: "Vitamin D3" → Extract as "vitamin d" + "d3" separately
- ✅ CORRECT: "Vitamin D3" → Extract as ONE ingredient "vitamin d3"
- ❌ WRONG: "Vitamin B12" → Extract as "vitamin b" + "b12" separately
- ✅ CORRECT: "Vitamin B12" → Extract as ONE ingredient "vitamin b12"
- ❌ WRONG: "Omega-3" → Extract as "omega" + "3" separately
- ✅ CORRECT: "Omega-3" → Extract as ONE ingredient "omega-3"

**Rule 2: Distinguish "Vitamin D" vs "Vitamin D3"**

- These are DIFFERENT ingredients in the database
- Only extract what's actually in the title - don't add or assume numbers
- "Vitamin D3 5000 IU" → Extract "vitamin d3" (specific form)
- "Vitamin D 5000 IU" → Extract "vitamin d" (generic)

**Rule 3: Skip Flavor Keywords (Unless Clearly Functional)**

- Don't extract: cherry, vanilla, chocolate, mint when used as flavors
- DO extract: "cherry extract 200mg", "peppermint oil capsules", "acai berry extract"
- Context clues for FLAVORS (skip): "flavored", "flavor", "taste", "natural"
- Context clues for INGREDIENTS (extract): "extract", "oil", "powder", dosage amounts

**Rule 4: Extract ALL Ingredients, Not Just the First**

- Find every functional ingredient in the title
- Call `lookup_ingredient()` for EACH one
- Return all ingredients with their positions

**Rule 5: Use Normalized Names from Tool Results**

- ⚠️ CRITICAL: Use the "ingredient" field from lookup_ingredient() response
- Don't use your raw extraction in the final output
- Example: Raw extraction "vitamin c" → Tool returns "VITAMIN C (NOT ESTER-C)" → Use "VITAMIN C (NOT ESTER-C)"

**Rule 6: Primary Ingredient Determination**

- PRIMARY = first ingredient by position in title
- EXCEPTION: If "multivitamin" is detected anywhere → it becomes primary regardless of position

**Examples:**

**Example 1: Single Ingredient**

- Title: "Vitamin D3 5000 IU 120 Softgels"
- Ingredients found: "vitamin d3" at position 0
- Tool call: `lookup_ingredient(ingredient_name="vitamin d3")`
- Tool returns: `{"ingredient": "VITAMIN D", "nw_category": "LETTER VITAMINS", "nw_subcategory": "VITAMIN D3", "found": true}`
- Output:
  ```json
  {
    "ingredients": [{"name": "VITAMIN D", "position": 0, "nw_category": "LETTER VITAMINS", "nw_subcategory": "VITAMIN D3"}],
    "primary_ingredient": "VITAMIN D"
  }
  ```

**Example 2: Multiple Ingredients**

- Title: "Vitamin D3 with Calcium and Magnesium 120 Softgels"
- Ingredients found:
  - "vitamin d3" at position 0
  - "calcium" at position 18
  - "magnesium" at position 30
- Tool calls: 3 separate calls for each ingredient
- Primary: "VITAMIN D" (first by position)

**Example 3: Multivitamin Override**

- Title: "Prenatal Multivitamin with DHA 60 Softgels"
- Ingredients found:
  - "multivitamin" at position 9
  - "dha" at position 30
- Primary: "MULTIPLE VITAMIN" (multivitamin overrides position rule)

**Exclusion Examples (from the file):**

**Case 1: Flavor vs Functional Ingredient**

- Title: "Cherry Flavored Multivitamin 60 Tablets"
- ✅ Extract: "multivitamin"
- ❌ Skip: "cherry" (flavor descriptor, not functional)

**Case 2: Functional Ingredient with Dosage**

- Title: "Acai Berry Extract 500mg Antioxidant 90 Capsules"
- ✅ Extract: "acai" (functional ingredient with dosage)
- ❌ Skip: none

**Case 3: Vanilla as Flavor**

- Title: "Vanilla Protein Shake Mix 2 lbs"
- ✅ Extract: "protein"
- ❌ Skip: "vanilla" (describes flavor of shake)

**Special Handling Cases:**

**Case 1: Probiotic Strain Not Found**

- Title: "Akkermansia Probiotic 300 Billion"
- Step 1: `lookup_ingredient(ingredient_name="akkermansia")` → returns found: false
- Step 2: Title contains "probiotic", so call `lookup_ingredient(ingredient_name="probiotic")` → returns "PROBIOTIC SUPPLEMENT" ✅

**Case 2: Combo Product**

- Title: "Echinacea Goldenseal Supreme"
- ✅ CORRECT: Try `lookup_ingredient(ingredient_name="echinacea goldenseal")` first
  - If found → Use "ECHINACEA GOLDENSEAL COMBO"
  - If not found → Split and look up separately
- ❌ WRONG: Immediately split into "echinacea" and "goldenseal"

---

**Advanced R System Features**

After the LLM extracts ingredients in Step 8, the system applies three advanced features matching the original R system:

**Note on Implementation:**

- **Feature 1 (Combo Detection):** Has TWO layers - LLM attempt (Step 8) + Python enforcement (Step 3)
- **Feature 2 (Protein Types):** Applied in **Step 3 post-processing** (Python code)
- **Feature 3 (Context-Dependent):** Applied by the **LLM in Step 8** (via prompt instructions)

**Feature 1: Ingredient Combo Detection (2-Layer Implementation)**

Automatically merges specific ingredient combinations (matching R system's FinalMerge.R logic):

**Layer 1 - LLM Attempt (Step 8):**

- The LLM is instructed via prompt to detect and merge combos during ingredient extraction
- If successful, ingredients are already merged when returned

**Layer 2 - Python Enforcement (Step 3):**

- Python code (`detect_ingredient_combos()`) enforces combo merging in post-processing
- This guarantees combos are merged even if LLM didn't do it
- Acts as a safety net to ensure consistency

**Combo 1: Glucosamine + Chondroitin**

- If both GLUCOSAMINE and CHONDROITIN are found
- Merge into: `GLUCOSAMINE CHONDROITIN COMBO`
- Category: `JOINT HEALTH`
- Example:
  - Before: ["GLUCOSAMINE", "CHONDROITIN", "MSM"]
  - After: ["GLUCOSAMINE CHONDROITIN COMBO", "MSM"]

**Combo 2: Vitamin B1 + B2 + B6 + B12**

- If all four B vitamins are found AND no other vitamins present
- Merge into: `VITAMIN B1 - B2 - B6 - B12`
- Category: `BASIC VITAMINS & MINERALS`
- Example:
  - Title: "B1 B2 B6 B12 Complex with Magnesium"
  - Before: ["VITAMIN B1 (THIAMIN)", "VITAMIN B2 (RIBOFLAVIN)", "VITAMIN B6 (PYRIDOXINE)", "VITAMIN B12", "MAGNESIUM"]
  - After: ["VITAMIN B1 - B2 - B6 - B12", "MAGNESIUM"]
  - Note: Magnesium is not a vitamin, so merge is OK

**Combo 3: Vitamin A + D**

- If both VITAMIN A and VITAMIN D are found AND no other vitamins present
- Merge into: `VITAMIN A & D COMBO`
- Category: `BASIC VITAMINS & MINERALS`
- Example:
  - Before: ["VITAMIN A", "VITAMIN D"]
  - After: ["VITAMIN A & D COMBO"]

**Implementation:**

**Layer 1 - LLM (Step 8):**

- **When:** During LLM ingredient extraction in Step 8
- **Code:** `src/llm/prompt_builder.py` loads combo rules into LLM prompt
- **Rules:** `reference_data/ingredient_extraction_rules.json` → `combo_detection` section
- **How:** LLM reads combo rules in prompt and attempts to merge before returning results

**Layer 2 - Python Enforcement (Step 3):**

- **When:** Step 3 post-processing (after LLM extraction, before business rules)
- **Code:** `src/pipeline/step3_postprocess.py` → `detect_ingredient_combos()` function
- **Rules:** Same JSON file as Layer 1
- **Triggered by:** `apply_postprocessing()` in main.py calls this function automatically
- **Purpose:** Safety net to guarantee combos are merged even if LLM missed them

---

**Feature 2: Granular Protein Type Detection (Step 3 Post-Processing)**

Automatically detects specific protein types with 200+ lines of logic matching R system's FI_CAT_Testing.R:

This runs in **Step 3 post-processing** as part of business rules when the primary ingredient is protein.

**Animal Proteins:**

- `PROTEIN - ANIMAL - WHEY` - Whey protein
- `PROTEIN - ANIMAL - CASEIN` - Casein protein
- `PROTEIN - ANIMAL - WHEY & CASEIN` - Both whey and casein
- `PROTEIN - ANIMAL - EGG` - Egg protein
- `PROTEIN - ANIMAL - MILK` - Milk protein
- `PROTEIN - ANIMAL - MILK & EGG` - Both milk and egg
- `PROTEIN - ANIMAL - WHEY & MILK` - Whey and milk combo
- `PROTEIN - ANIMAL - WHEY & EGG` - Whey and egg combo
- `PROTEIN - ANIMAL - MEAT` - Beef/chicken/fish protein
- `PROTEIN - ANIMAL - INSECT` - Insect protein
- `PROTEIN - ANIMAL - MULTI` - Multiple animal proteins (3+)
- `PROTEIN - ANIMAL - GENERAL` - General animal protein

**Plant Proteins:**

- `PROTEIN - PLANT - PEA` - Pea protein
- `PROTEIN - PLANT - RICE` - Rice protein
- `PROTEIN - PLANT - SOY` - Soy protein
- `PROTEIN - PLANT - HEMP` - Hemp protein
- `PROTEIN - PLANT - MULTI` - Multiple plant proteins (2+)
- `PROTEIN - PLANT - GENERAL` - General plant protein

**Combo:**

- `PROTEIN - ANIMAL & PLANT COMBO` - Mix of animal and plant proteins

**How It Works:**

1. Checks title for plant keywords: pea, rice, soy, hemp, alfalfa, baobab
2. Checks title for animal keywords: casein, egg, insect, beef, chicken, fish, meat, milk, whey
3. Counts plant vs animal proteins
4. Applies decision tree matching R system logic:
   - Both plant + animal → COMBO
   - Multiple plant (2+) → PLANT - MULTI
   - Single plant → Specific type (PEA, RICE, SOY, HEMP)
   - Multiple animal (2) → Check for common pairs (WHEY & CASEIN, etc.)
   - Multiple animal (3+) → ANIMAL - MULTI
   - Single animal → Specific type (WHEY, CASEIN, EGG, MEAT, etc.)

**Examples:**

| Product Title                | Detected Type                    | Logic                   |
| ---------------------------- | -------------------------------- | ----------------------- |
| "Whey Protein Isolate 2 lbs" | PROTEIN - ANIMAL - WHEY          | Single animal keyword   |
| "Pea Protein Powder Vegan"   | PROTEIN - PLANT - PEA            | Single plant keyword    |
| "Whey Casein Blend 5 lbs"    | PROTEIN - ANIMAL - WHEY & CASEIN | Common animal pair      |
| "Pea Rice Protein Organic"   | PROTEIN - PLANT - MULTI          | Multiple plant keywords |
| "Whey Pea Protein Blend"     | PROTEIN - ANIMAL & PLANT COMBO   | Both plant and animal   |

**Implementation:**

- **When:** Step 3 post-processing (during business rules application)
- **Code:** `src/pipeline/utils/business_rules.py` → `detect_granular_protein_type()` function
- **Triggered by:** `apply_all_business_rules()` when primary ingredient contains "protein"
- **Effect:** Overrides subcategory with granular protein type (e.g., PROTEIN - ANIMAL - WHEY)

---

**Feature 3: Context-Dependent Ingredients (LLM in Step 8)**

Some ingredients require context to identify correctly (matching R system special case logic):

This is handled by the **LLM in Step 8** via prompt instructions. The LLM checks context rules BEFORE calling `lookup_ingredient()` tool.

**Case 1: Angelica vs Dong Quai**

- Rule: If title contains "angelica" AND "dong quai" → lookup "dong quai"
- Otherwise → lookup "angelica"
- Reasoning: Dong Quai is a specific type of Angelica, takes priority
- Example: "Angelica Dong Quai Extract" → Use "DONG QUAI"

**Case 2: Arnica (Homeopathic vs Herbal)**

- Rule: If title contains "arnica" AND "homeopathic" → lookup "arnica homeopathic"
- Otherwise → lookup "arnica herbal"
- Reasoning: Homeopathic and herbal arnica are different products
- Example: "Arnica Homeopathic 30C Pellets" → Use "ARNICA HOMEOPATHIC"

**Case 3: Holy Basil vs Basil**

- Rule: If "holy" appears near "basil" → lookup "holy basil"
- Otherwise → lookup "basil"
- Reasoning: Holy Basil (Tulsi) is different from culinary basil
- Example: "Holy Basil Organic Capsules" → Use "HOLY BASIL (TULSI)"

**Case 4: Ubiquinol vs CoQ10**

- Rule: If "ubiquinol" in title → lookup "ubiquinol"
- Else if "coq10" in title → lookup "coq10"
- Reasoning: Ubiquinol is a specific form of CoQ10
- Example: "Ubiquinol 100mg Softgels" → Use "UBIQUINOL"

**Implementation:**

- **When:** Step 8 (LLM ingredient extraction) - BEFORE calling `lookup_ingredient()` tool
- **Code:** Rules loaded into LLM prompt by `src/llm/prompt_builder.py`
- **Rules:** `reference_data/ingredient_extraction_rules.json` → `context_dependent_ingredients` section
- **How it works:** LLM reads context rules in prompt, checks title context, then calls correct lookup
- **Example flow:** Title has "arnica" + "homeopathic" → LLM calls `lookup_ingredient("arnica homeopathic")` not `lookup_ingredient("arnica")`

**Defined in JSON:**

```json
"context_dependent_ingredients": {
  "description": "Some ingredients require context to identify correctly",
  "cases": [
    {
      "primary_keyword": "angelica",
      "rule": "If title contains 'angelica' AND 'dong quai' → lookup 'dong quai', otherwise → lookup 'angelica'",
      "reasoning": "Dong Quai is a specific type of Angelica, takes priority"
    },
    ...
  ],
  "instruction": "Before calling lookup_ingredient(), check these context rules."
}
```

---

**How to Modify:**

**Modifying Extraction Rules (ingredient_extraction_rules.json):**

1. **Download the file** from S3: `reference_data/ingredient_extraction_rules.json`
2. **Edit the JSON file**:

   - To add new flavor keywords: Add to `exclusions.flavor_keywords` array
   - To add new multivitamin keywords: Add to `special_cases.multivitamin.keywords` array
   - To add new protein keywords: Add to `special_cases.protein.keywords` array
   - To add new extraction examples: Add to `exclusions.examples` array
   - To add new critical rules: Add to `critical_rules` array
   - **To add new ingredient combos:** Add to `special_handling.combo_detection.combos` array
   - **To add new context-dependent ingredients:** Add to `special_handling.context_dependent_ingredients.cases` array

**Example 1 - Adding "mango" as a flavor keyword:**

Before:

```json
"flavor_keywords": ["cherry", "acai", "cranberry", "blueberry", "blackberry", "peppermint", "vanilla", "chocolate", ...]
```

After:

```json
"flavor_keywords": ["cherry", "acai", "cranberry", "blueberry", "blackberry", "peppermint", "vanilla", "chocolate", "mango", "peach", ...]
```

**Example 2 - Adding a new multivitamin keyword:**

Before:

```json
"multivitamin": {
  "keywords": ["multivitamin", "multi vitamin", "multi-vitamin", "multiple vitamin"]
}
```

After:

```json
"multivitamin": {
  "keywords": ["multivitamin", "multi vitamin", "multi-vitamin", "multiple vitamin", "daily vitamin"]
}
```

**Example 3 - Adding a new ingredient combo (Vitamin E + Selenium):**

Add this to `special_handling.combo_detection.combos` array:

```json
{
  "combo_name": "VITAMIN E & SELENIUM COMBO",
  "required_ingredients": ["vitamin e", "selenium"],
  "condition": "Only merge if NO other vitamins are present",
  "action": "Replace VITAMIN E with 'VITAMIN E & SELENIUM COMBO' and remove SELENIUM from the list",
  "example": {
    "before": ["VITAMIN E", "SELENIUM"],
    "after": ["VITAMIN E & SELENIUM COMBO"]
  }
}
```

**Example 4 - Adding a context-dependent ingredient (Ginseng types):**

Add this to `special_handling.context_dependent_ingredients.cases` array:

```json
{
  "primary_keyword": "ginseng",
  "rule": "If 'korean' or 'panax' appears near 'ginseng' → lookup 'korean ginseng', else if 'american' → lookup 'american ginseng', else if 'siberian' → lookup 'siberian ginseng'",
  "reasoning": "Different ginseng types have different properties"
}
```

3. **Upload the updated file** to S3 bucket **reference/** folder

---

**Modifying Ingredient Database (ingredient_category_lookup.csv):**

To add or update ingredient mappings:

1. **Download the file** from S3: `reference_data/ingredient_category_lookup.csv`
2. **Edit the CSV file** - Add new rows or modify existing ones:

| INGREDIENT              | NW_CATEGORY     | NW_SUBCATEGORY |
| ----------------------- | --------------- | -------------- |
| ASHWAGANDHA             | HERBS           | SINGLES        |
| VITAMIN C (NOT ESTER-C) | LETTER VITAMINS | VITAMIN C      |

**Example - Adding a new ingredient "Lion's Mane":**

Add this row to the CSV:

```csv
LION'S MANE,HERBS,SINGLES
```

**Example - Updating an existing ingredient:**

Change:

```csv
TURMERIC,HERBS,SINGLES
```

To:

```csv
TURMERIC,HERBS,TURMERIC & CURCUMIN
```

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process products with the new/updated ingredients
5. Next processing run will use the updated database

---

**⚠️ Note on Granular Protein Type Detection:**

The granular protein type detection logic is implemented in Python code (`src/pipeline/utils/business_rules.py` → `detect_granular_protein_type()` function), not in JSON reference files. This is because it involves complex decision tree logic (200+ lines) that matches the R system's FI_CAT_Testing.R.

To modify protein type detection:

- Edit `src/pipeline/utils/business_rules.py`
- Modify the `detect_granular_protein_type()` function
- Update keyword lists: `plant_keywords` and `animal_keywords`
- Modify decision tree logic as needed
- Requires Docker image rebuild for AWS deployment

**Note:** Ingredient combos and context-dependent ingredients are in JSON files and can be updated via S3 without code changes. Protein detection requires code changes because of its complexity.

---

### 2.10 Potency Extraction (Step 9 in LLM)

**What It Does:**

The LLM extracts the potency/strength/dosage of the PRIMARY ingredient only (determined in Step 8). This is typically expressed as a number followed by a unit (mg, IU, mcg, billion, etc.).

**⚠️ CRITICAL:**

- Potency is extracted ONLY for the primary ingredient, NOT for secondary ingredients
- It's different from size/count (60 capsules ≠ potency)
- Probiotics return numeric value only, vitamins/minerals include units

**Reference File:** `reference_data/potency_extraction_rules.json`

**File Structure:**

```json
{
  "context_reminder": "⚠️  REMINDER: You just extracted ingredients in STEP 8 and identified the PRIMARY ingredient. Now extract potency ONLY for that PRIMARY ingredient!",
  "instructions": "Extract the potency/strength/dosage of the primary ingredient from the product title...",
  "priority_order": [
    {
      "priority": 1,
      "name": "Probiotics - Billion CFU",
      "pattern_examples": ["50 billion CFU", "100B", "30 billion"],
      "unit": "billion",
      "extraction": "Extract numeric value only"
    },
    {
      "priority": 2,
      "name": "Vitamins/Minerals - Standard Units",
      "pattern_examples": ["5000 IU", "500mg", "100 mcg"],
      "unit": "varies (IU, mg, mcg, g)",
      "extraction": "Extract number + unit"
    },
    {
      "priority": 3,
      "name": "Percentage Concentration",
      "pattern_examples": ["95% curcumin", "80% omega-3"],
      "unit": "%",
      "extraction": "Extract number + %"
    }
  ],
  "critical_rules": [ /* 6 critical rules */ ],
  "examples": [ /* 8 examples */ ],
  "edge_cases": [ /* 4 edge cases */ ],
  "default": "",
  "default_reasoning": "No clear potency stated for primary ingredient"
}
```

**Fields Used by the System:**

- `context_reminder` - Reminder that primary ingredient was already identified in Step 8
- `instructions` - Main instructions sent to LLM
- `priority_order` - 3 extraction types (probiotics, vitamins/minerals, percentages)
- `critical_rules` - Rules about what to extract and what to ignore
- `examples` - 8 example extractions
- `edge_cases` - 4 complex scenarios with correct/wrong answers
- `default` - Empty string "" if no potency found
- `default_reasoning` - Explanation for default

**Valid Output Values:**

- **For probiotics:** Numeric value only: `"50"`, `"100"`, `"30"`
- **For vitamins/minerals:** Number + unit: `"5000 IU"`, `"500mg"`, `"100 mcg"`
- **For percentages:** Number + %: `"95%"`
- **Default:** `""` (empty string) if no clear potency

**How It Works - Priority Order:**

**Priority 1: Probiotics (Billion CFU)**

- Patterns: "50 billion CFU", "100B", "30 billion", "1 bil", "50B CFU", "100 billion live cultures"
- Extraction: Extract ONLY the numeric value
  - "50 billion CFU" → "50"
  - "100B" → "100"
- Why: Probiotics measured in billions of CFU (Colony Forming Units)

**Priority 2: Vitamins/Minerals (Standard Units)**

- Patterns: "5000 IU", "500mg", "100 mcg", "1000 mg", "25mcg"
- Extraction: Extract number + unit
  - "5000 IU" → "5000 IU"
  - "500mg" → "500mg"
- Why: Standard supplement measurement units

**Priority 3: Percentage Concentration**

- Patterns: "95% curcumin", "80% omega-3"
- Extraction: Extract number + %
  - "95% curcumin" → "95%"
- Why: Some extracts show concentration as percentage

**⚠️ Critical Rules:**

1. **ONLY extract potency for PRIMARY ingredient** (determined in Step 8)
2. **Do NOT extract count/quantity**
   - ❌ WRONG: "60 capsules" → potency: "60"
   - ✅ CORRECT: "5000 IU vitamin D 60 capsules" → potency: "5000 IU"
3. **For probiotics:** Extract ONLY the number, without "billion"
   - ✅ "50 billion CFU" → "50"
   - ✅ "100B" → "100"
4. **For vitamins/minerals:** Include the unit
   - ✅ "Vitamin D3 5000 IU" → "5000 IU"
5. **If multiple dosages:** Extract PRIMARY ingredient's dosage only
   - "Calcium 500mg with Vitamin D 1000 IU" → "500mg" (calcium is primary)
6. **If no potency:** Return empty string ""

**Examples:**

| Product Title                                        | Primary Ingredient | Potency | Reasoning                                |
| ---------------------------------------------------- | ------------------ | ------- | ---------------------------------------- |
| "Probiotic 50 Billion CFU 30 Capsules"               | probiotic          | 50      | Numeric value only                       |
| "Vitamin D3 5000 IU 120 Softgels"                    | vitamin d3         | 5000 IU | Primary ingredient potency               |
| "Turmeric 500mg with Black Pepper 60 Capsules"       | turmeric           | 500mg   | Primary is 500mg                         |
| "Fish Oil 1000mg (EPA 180mg DHA 120mg) 180 Softgels" | fish oil           | 1000mg  | Total is 1000mg (EPA/DHA are components) |
| "Magnesium 200mg with Vitamin B6 25mg 90 Capsules"   | magnesium          | 200mg   | Primary is 200mg, B6 secondary           |
| "Multivitamin for Women 60 Tablets"                  | multivitamin       | (empty) | No single potency (mix of nutrients)     |
| "Ultimate Flora Probiotic 100B 30 Capsules"          | probiotic          | 100     | 100B = 100 billion, numeric only         |

**Edge Cases:**

**Case 1: Dosage AND Count in same title**

- Example: "Vitamin C 1000mg 100 Tablets"
- ✅ Correct: "1000mg" (potency per serving)
- ❌ Wrong: "100" (that's count)

**Case 2: Multiple ingredients with different potencies**

- Example: "Calcium 600mg Magnesium 400mg Zinc 15mg"
- ✅ Correct: "600mg" (extract ONLY primary ingredient's potency)

**Case 3: Concentration percentage**

- Example: "Curcumin Extract 95% Standardized 500mg"
- ✅ Correct: "500mg" (the potency)
- Note: 95% is extract standardization, not potency

**Case 4: No clear potency**

- Example: "Hair, Skin & Nails Formula 60 Capsules"
- ✅ Correct: "" (empty string)

**How to Modify:**

1. **Download the file** from S3: `reference_data/potency_extraction_rules.json`
2. **Edit the JSON file**:

   - To add new pattern examples: Add to `priority_order[].pattern_examples`
   - To add new examples: Add to `examples` array
   - To add new edge cases: Add to `edge_cases` array
   - To add new critical rules: Add to `critical_rules` array

**Example 1 - Adding new probiotic patterns:**

Before:

```json
"pattern_examples": ["50 billion CFU", "100B", "30 billion", "1 bil", "50B CFU", "100 billion live cultures"]
```

After:

```json
"pattern_examples": ["50 billion CFU", "100B", "30 billion", "1 bil", "50B CFU", "100 billion live cultures", "50 bil CFU", "30bn", "50B live cultures"]
```

**Example 2 - Adding a new example:**

Add to `examples` array:

```json
{
  "title": "CoQ10 200mg Ubiquinone with BioPerine 120 Capsules",
  "primary_ingredient": "coq10",
  "potency": "200mg",
  "reasoning": "Primary ingredient (CoQ10) has potency of 200mg, BioPerine is secondary"
}
```

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process products with various potency formats
5. Next processing run will use the updated patterns

---

### 2.11 Business Rules Application (Step 10 in LLM)

After extracting all ingredients (Step 8), the LLM calls the `apply_business_rules()` tool to determine the final category and subcategory. This tool applies deterministic business logic to refine the category based on title keywords, primary ingredient, and extracted attributes.

**What This Step Does:**

1. **Receives All Ingredients**: Gets the complete list of ingredients extracted in Step 8
2. **Identifies Primary Ingredient**: Determines which ingredient is primary (first by position, or multivitamin override)
3. **Applies 5 Business Rules in Order**: Each rule can override the previous one
4. **Returns Final Category/Subcategory**: Along with reasoning for any changes made

**Reference File:** `reference_data/business_rules.json`

**The 5 Business Rules (Applied in Order):**

**Rule 1: Title-Based Overrides (Priority 1)**

Checks the product title for specific keywords that always override the category:

- **"PROTEIN POWDER"** → Category: ACTIVE NUTRITION, Subcategory: PROTEIN & MEAL REPLACEMENTS
- **"WEIGHT LOSS" or "WEIGHT MANAGEMENT"** → Category: ACTIVE NUTRITION, Subcategory: WEIGHT MANAGEMENT

**Example:**
- Title: "Whey Protein Powder Vanilla 2lb"
- Even if ingredient lookup says "SPORTS NUTRITION", title override changes it to "ACTIVE NUTRITION / PROTEIN & MEAL REPLACEMENTS"

**Rule 2: Ingredient-Specific Overrides (Priority 2)**

Certain primary ingredients always go to specific categories:

- **SAM-E** → MISCELLANEOUS SUPPLEMENTS / MISCELLANEOUS SUPPLEMENTS
- **Algae products** (Spirulina, Chlorella, Sea Moss) → HERBAL REMEDIES / FOOD SUPPLEMENTS
- **Echinacea Goldenseal Combo** → HERBAL/HOMEOPATHIC COLD & FLU / HERBAL FORMULAS COLD & FLU
- **Choline Inositol** → MISCELLANEOUS SUPPLEMENTS / MISCELLANEOUS SUPPLEMENTS
- **Ubiquinol** → COENZYME Q10 / COENZYME Q10
- **Glandular** → MISCELLANEOUS SUPPLEMENTS / MISCELLANEOUS SUPPLEMENTS

**Example:**
- Primary Ingredient: "SPIRULINA"
- Override: Category → HERBAL REMEDIES, Subcategory → FOOD SUPPLEMENTS

**Rule 3: Protein Category Override (Priority 3)**

All protein ingredients go to SPORTS NUTRITION:

- Primary ingredient contains: PROTEIN, WHEY, ISOLATE, CASEIN, PEA PROTEIN, SOY PROTEIN
- Override: Category → SPORTS NUTRITION, Subcategory → PROTEIN

**Example:**
- Primary Ingredient: "WHEY PROTEIN ISOLATE"
- Category → SPORTS NUTRITION, Subcategory → PROTEIN

**Rule 4: Herb Formula Logic (Priority 4)**

For HERBAL REMEDIES category, determines if product is FORMULAS or SINGLES:

- **2+ herbs** → Subcategory: FORMULAS
- **1 herb** → Subcategory: SINGLES

**Example:**
- Ingredients: ["TURMERIC", "GINGER", "BLACK PEPPER"]
- Category: HERBAL REMEDIES (from ingredient lookup)
- Count herbs: 2 (Turmeric, Ginger are herbs; Black Pepper is not)
- Subcategory → FORMULAS

**Rule 5: Multivitamin Refinement (Priority 5 - Highest)**

For COMBINED MULTIVITAMINS category, refines subcategory based on age and gender:

**Age-Based (Highest Priority):**
- Age = CHILD → Subcategory: CHILD
- Age = TEEN → Subcategory: TEEN

**Age + Gender Combination:**
- Gender = MALE + Age = ADULT → Subcategory: MEN
- Gender = MALE + Age = MATURE ADULT → Subcategory: MEN MATURE
- Gender = FEMALE + Age = ADULT → Subcategory: WOMEN
- Gender = FEMALE + Age = MATURE ADULT → Subcategory: WOMEN MATURE
- Gender = NON SPECIFIC + Age = ADULT → Subcategory: ADULT
- Gender = NON SPECIFIC + Age = MATURE ADULT → Subcategory: MATURE ADULT

**Title Override (Overrides Everything Above):**
- Title contains "PRENATAL" or "POSTNATAL" → Subcategory: PRENATAL (highest priority!)

**Examples:**

| Product Title | Gender | Age | Initial Subcategory | Final Subcategory | Rule Applied |
|--------------|--------|-----|---------------------|-------------------|--------------|
| "Women's Multivitamin 60 Tablets" | FEMALE | ADULT | COMBINED MULTIVITAMINS | WOMEN | Gender + Age |
| "Men's 50+ Multivitamin" | MALE | MATURE ADULT | COMBINED MULTIVITAMINS | MEN MATURE | Gender + Age |
| "Prenatal Multivitamin for Women" | FEMALE | ADULT | COMBINED MULTIVITAMINS | PRENATAL | Title override |
| "Kids Multivitamin Gummies" | NON SPECIFIC | CHILD | COMBINED MULTIVITAMINS | CHILD | Age-based |

**Output from `apply_business_rules()` Tool:**

The tool returns:

```json
{
  "initial_category": "COMBINED MULTIVITAMINS",
  "initial_subcategory": "COMBINED MULTIVITAMINS",
  "final_category": "COMBINED MULTIVITAMINS",
  "final_subcategory": "WOMEN",
  "primary_ingredient": "MULTIPLE VITAMIN",
  "has_changes": true,
  "changes_made": ["Subcategory: COMBINED MULTIVITAMINS → WOMEN"],
  "has_unknown": false,
  "should_explain": true,
  "reasoning_context": "Multivitamin refined to WOMEN based on female gender and adult age"
}
```

**When the LLM Should Provide Reasoning:**

The LLM ONLY provides reasoning when `should_explain` is TRUE (meaning changes were made or UNKNOWN values were found).

**Good reasoning examples:**
- "CoQ10 triggered subcategory override from MINERALS to COENZYME Q10"
- "Multivitamin refined to WOMEN MATURE based on female gender and mature adult age"
- "Title contains 'protein powder' which overrode category to ACTIVE NUTRITION"

**How to Modify:**

1. **Download the file** from S3: `reference_data/business_rules.json`

2. **Edit the JSON file** to add or modify rules:

**Example 1 - Adding a new title-based override:**

Add to `rules[0].conditions`:

```json
{
  "if": "title contains 'PRE-WORKOUT' or 'PRE WORKOUT'",
  "then": {
    "category": "SPORTS NUTRITION",
    "subcategory": "PRE-WORKOUT"
  },
  "reasoning": "Pre-workout products go to sports nutrition"
}
```

**Example 2 - Adding a new ingredient-specific override:**

Add to `rules[1].conditions`:

```json
{
  "if": "primary_ingredient = 'BERBERINE'",
  "then": {
    "category": "BLOOD SUGAR SUPPORT",
    "subcategory": "BLOOD SUGAR SUPPORT"
  }
}
```

**Example 3 - Modifying multivitamin refinement:**

To add a new age/gender combination, edit `rules[4].conditions[0].logic.priority_2_age_and_gender`:

```json
{
  "if": "gender = 'GENDER - FEMALE' AND age = 'AGE GROUP - SENIOR'",
  "then": {"subcategory": "WOMEN SENIOR"}
}
```

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process sample products to verify the rules work as expected
5. Next processing run will automatically use the updated rules

**Important Notes:**

- Rules are applied IN ORDER (1-5)
- Later rules override earlier rules
- For multivitamins, PRENATAL title override is the HIGHEST priority
- The LLM must call this tool AFTER extracting all ingredients

---

### 2.12 Post-Processing (Step 11 in LLM - FINAL STEP)

After calling `apply_business_rules()`, the LLM calls the `apply_postprocessing()` tool to perform final processing and get complete results. This is the **FINAL STEP** that combines all processing into one cohesive result.

**What This Tool Does:**

The `apply_postprocessing()` tool performs 4 critical operations:

1. **Enforces Ingredient Combos** - Merges specific ingredient combinations (Glucosamine+Chondroitin, B vitamins, A+D)
2. **Re-applies Business Rules** - In case combos changed the primary ingredient, category/subcategory are recalculated
3. **Assigns Health Focus** - Maps primary ingredient to health category (e.g., "BONE HEALTH", "JOINT HEALTH")
4. **Assigns High-Level Category** - Determines PRIORITY VMS / NON-PRIORITY VMS / OTC / REMOVE

**Reference File:** `reference_data/postprocessing_rules.json`

This JSON file contains:
- **Ingredient combo rules** (3 combos with merge logic)
- **High-level category mapping** (4 rules for HLC assignment)

**Why This Tool Exists:**

The LLM needs to generate reasoning based on the **FINAL** results (after combos are merged). Without this tool, the LLM would generate reasoning based on pre-combo ingredients, which could be inaccurate.

**Example: Combo Detection Changes Everything**

**Without Post-Processing Tool:**
- LLM extracts: ["GLUCOSAMINE", "CHONDROITIN", "MSM"]
- Primary ingredient: GLUCOSAMINE
- LLM reasoning: "Primary ingredient is GLUCOSAMINE"
- Python later merges combo → "GLUCOSAMINE CHONDROITIN COMBO"
- **Problem:** LLM reasoning doesn't mention the combo!

**With Post-Processing Tool:**
- LLM extracts: ["GLUCOSAMINE", "CHONDROITIN", "MSM"]
- Calls `apply_postprocessing()` → merges combo
- Final ingredients: ["GLUCOSAMINE CHONDROITIN COMBO", "MSM"]
- LLM reasoning: "Combo detected: Glucosamine + Chondroitin | Final: JOINT HEALTH / GLUCOSAMINE & CHONDROITIN"
- **Solution:** LLM reasoning is accurate and complete!

**Tool Output:**

The tool returns:

```json
{
  "combo_detected": true,
  "combos_applied": ["Glucosamine + Chondroitin"],
  "ingredients_before_combo": ["GLUCOSAMINE", "CHONDROITIN", "MSM"],
  "ingredients_after_combo": ["GLUCOSAMINE CHONDROITIN COMBO", "MSM"],
  "final_category": "JOINT HEALTH",
  "final_subcategory": "GLUCOSAMINE & CHONDROITIN",
  "primary_ingredient": "GLUCOSAMINE CHONDROITIN COMBO",
  "health_focus": "JOINT HEALTH",
  "high_level_category": "PRIORITY VMS",
  "reasoning_context": "Combo detected: Glucosamine + Chondroitin | Final: JOINT HEALTH / GLUCOSAMINE & CHONDROITIN | Health focus: JOINT HEALTH | High-level category: PRIORITY VMS"
}
```

**The 3 Ingredient Combos (from JSON):**

**Combo 1: Glucosamine + Chondroitin**
- Merges into "GLUCOSAMINE CHONDROITIN COMBO"
- Category: JOINT HEALTH / GLUCOSAMINE & CHONDROITIN

**Combo 2: Vitamin B1 + B2 + B6 + B12** (only if NO other vitamins)
- Merges into "VITAMIN B1 - B2 - B6 - B12"
- Category: BASIC VITAMINS & MINERALS / LETTER VITAMINS

**Combo 3: Vitamin A + D** (only if NO other vitamins)
- Merges into "VITAMIN A & D COMBO"
- Category: BASIC VITAMINS & MINERALS / LETTER VITAMINS

**Health Focus Categories:**

The tool assigns health focus based on the primary ingredient using `ingredient_health_focus_lookup.csv`:

- BONE HEALTH
- BRAIN HEALTH
- CARDIOVASCULAR HEALTH
- DIGESTIVE HEALTH
- ENERGY SUPPORT
- EYE HEALTH
- IMMUNE HEALTH
- JOINT HEALTH
- MOOD & STRESS SUPPORT
- And 15+ more categories...

**High-Level Category Rules (from JSON):**

1. **IF category = "OTC"** → "OTC"
2. **IF category = "REMOVE" or null** → "REMOVE"
3. **IF category = "ACTIVE NUTRITION"** → "NON-PRIORITY VMS"
4. **All other categories** → "PRIORITY VMS"

**How to Modify:**

1. **Download the file** from S3: `reference_data/postprocessing_rules.json`

2. **Edit the JSON file**:

**Example 1 - Adding a new ingredient combo:**

Add to `ingredient_combos.combos` array:

```json
{
  "combo_id": "COMBO-04",
  "combo_name": "CALCIUM MAGNESIUM ZINC COMBO",
  "required_ingredients": ["calcium", "magnesium", "zinc"],
  "match_mode": "contains",
  "merge_action": {
    "keep_position": "first",
    "combo_category": "BONE HEALTH",
    "combo_subcategory": "CALCIUM & MAGNESIUM"
  },
  "description": "Merge Calcium, Magnesium, and Zinc into combo"
}
```

**Example 2 - Changing high-level category mapping:**

Modify `high_level_category_mapping.rules`:

```json
{
  "rule_id": "HLC-05",
  "priority": 5,
  "condition": "category equals 'SPORTS NUTRITION'",
  "high_level_category": "NON-PRIORITY VMS",
  "description": "Sports nutrition products"
}
```

3. **Upload the updated file** to S3 bucket **reference/** folder
4. **Test**: Process products to verify the new rules work
5. Next processing run will use the updated rules

**Important Notes:**

- This tool MUST be called after `apply_business_rules()`
- The LLM uses the `reasoning_context` field for its final reasoning
- All rules are configurable via JSON (no code changes needed)
- The tool is called inside the LLM, so reasoning is accurate

---

**Complete LLM Output at This Stage:**

After completing all 11 steps (Safety Check → Age → Gender → Form → Organic → Pack Count → Unit → Size → Ingredient → Potency → Business Rules → **Post-Processing**), the LLM returns a complete JSON object with all extracted attributes:

```json
{
  "age": {
    "value": "AGE GROUP - ADULT",
    "reasoning": "No specific age keywords found, defaulting to ADULT"
  },
  "gender": {
    "value": "GENDER - FEMALE",
    "reasoning": "Title contains 'women's' indicating female target audience"
  },
  "form": {
    "value": "SOFTGEL",
    "reasoning": "Title contains 'softgels' which is the delivery form"
  },
  "organic": {
    "value": "N/A",
    "reasoning": "No organic certification keywords found"
  },
  "count": {
    "value": "120",
    "reasoning": "Title contains '120 softgels' indicating count"
  },
  "unit": {
    "value": "N/A",
    "reasoning": "No weight/volume unit found (IU is potency unit, not product unit)"
  },
  "size": {
    "value": "1",
    "reasoning": "No pack keywords found, defaulting to single pack"
  },
  "potency": {
    "value": "5000 IU",
    "reasoning": "Primary ingredient (Vitamin D3) has potency of 5000 IU"
  },
  "ingredients": [
    {
      "name": "VITAMIN D3",
      "position": 1,
      "category": "LETTER VITAMINS",
      "subcategory": "VITAMIN D"
    }
  ],
  "primary_ingredient": "VITAMIN D3",
  "business_rules": {
    "initial_category": "LETTER VITAMINS",
    "initial_subcategory": "VITAMIN D",
    "final_category": "LETTER VITAMINS",
    "final_subcategory": "VITAMIN D",
    "primary_ingredient": "VITAMIN D3",
    "has_changes": false,
    "changes_made": [],
    "has_unknown": false,
    "should_explain": false,
    "reasoning": ""
  },
  "postprocessing": {
    "combo_detected": false,
    "combos_applied": [],
    "ingredients_after_combo": ["VITAMIN D3"],
    "final_category": "LETTER VITAMINS",
    "final_subcategory": "VITAMIN D",
    "primary_ingredient": "VITAMIN D3",
    "health_focus": "BONE HEALTH",
    "high_level_category": "PRIORITY VMS",
    "reasoning": "Final classification: LETTER VITAMINS / VITAMIN D | Health focus: BONE HEALTH | High-level category: PRIORITY VMS"
  }
}
```

**What Happens Next:**

This complete JSON output is saved to `audit/step2_llm/{asin}.json`. The postprocessing results are already complete - no additional Python processing needed! The system extracts the final values from the `postprocessing` field and writes them to the output CSV.

**Key Fields from Post-Processing:**
- `combo_detected` - Boolean indicating if ingredient combos were merged
- `combos_applied` - Array of combo names (e.g., ["Glucosamine + Chondroitin"])
- `final_category` / `final_subcategory` - Category after combo enforcement
- `health_focus` - Health category (e.g., "BONE HEALTH", "JOINT HEALTH")
- `high_level_category` - PRIORITY VMS / NON-PRIORITY VMS / OTC / REMOVE
- `reasoning` - Complete summary for audit trail

---

## Step 3: Extract Results & Final Output

After the LLM completes all 11 steps (including post-processing), the system extracts the final results and prepares the output CSV.

### What Step 3 Does

**Important:** Post-processing (combos, health focus, high-level category) is now **handled by the LLM tool** in Step 2.12. Step 3 simply extracts the results from the LLM's JSON output and performs one final operation:

1. **Extract Post-Processing Results from LLM** - Reads the `postprocessing` field from LLM's JSON output
2. **Weight Unit Conversion (Optional)** - If product has weight units (lb, kg, g, mg, ml), converts to OZ

**Why This Change:**

Previously, post-processing ran twice: once in the LLM (generating reasoning) and again in Python (actual processing). This caused:
- Redundant processing
- Inaccurate LLM reasoning (based on pre-combo ingredients)
- Wasted compute resources

Now, post-processing runs **once inside the LLM**, so the LLM generates reasoning based on the **final** results (after combos, with health focus and HLC).

**Reference Files Used:**
- `unit_extraction_rules.json` - Contains conversion factors for weight units (only file used in Step 3)

---

### 3.1 Post-Processing Results (Handled by LLM)

**Important:** Ingredient combo enforcement, business rules, health focus assignment, and high-level category assignment are now **handled by the LLM** in Step 2.12 via the `apply_postprocessing()` tool.

**See Section 2.12** for complete documentation on:
- Ingredient combo detection (Glucosamine+Chondroitin, B vitamins, A+D)
- Business rules re-application
- Health focus assignment
- High-level category mapping
- How to modify `postprocessing_rules.json`

The Python code in Step 3 simply **extracts** these results from the LLM's JSON output.

---

### 3.2 Weight Unit Conversion (Python Processing)

This is the **ONLY** Python post-processing step that remains. All other post-processing (combos, health focus, HLC) is handled by the LLM tool in Step 2.12.

For products measured by weight, the system converts various weight units to OZ (ounces) to standardize the output.

**When Conversion Happens:**

- Only for products where `unit` = lb, kg, g, mg, or ml
- NOT for products where `unit` = COUNT, OZ, N/A, or UNKNOWN

**Conversion Factors (from `unit_extraction_rules.json`):**

| Original Unit | Conversion Factor | Result Unit |
|--------------|------------------|-------------|
| lb (pounds) | × 16.0 | OZ |
| kg (kilograms) | × 35.274 | OZ |
| g (grams) | × 0.035274 | OZ |
| mg (milligrams) | × 0.000035274 | OZ |
| ml (milliliters) | × 0.033814 | OZ |
| OZ (ounces) | No conversion | OZ |
| COUNT | No conversion | COUNT |

**Examples:**

| Original Size | Original Unit | Converted Size | Converted Unit | Calculation |
|--------------|--------------|---------------|---------------|-------------|
| 2 | lb | 32.0 | OZ | 2 × 16.0 = 32.0 |
| 1 | kg | 35.274 | OZ | 1 × 35.274 = 35.274 |
| 500 | g | 17.637 | OZ | 500 × 0.035274 = 17.637 |
| 1000 | mg | 0.035 | OZ | 1000 × 0.000035274 = 0.035 |
| 250 | ml | 8.454 | OZ | 250 × 0.033814 = 8.454 |
| 16 | OZ | 16 | OZ | No conversion |
| 120 | COUNT | 120 | COUNT | No conversion (discrete units) |

**Why Convert to OZ?**

Standardizing all weight measurements to OZ makes it easier to:
- Compare product sizes across different brands
- Sort products by size
- Match R system's output format exactly

**Code Location:** `src/pipeline/utils/unit_converter.py` → `convert_weight_to_oz()`

**How to Modify Conversion Factors:**

The conversion factors are stored in `reference_data/unit_extraction_rules.json`:

1. **Download the file** from S3: `reference_data/unit_extraction_rules.json`

2. **Find the `conversion_factors_for_python` section**:

```json
"conversion_factors_for_python": {
  "lb": 16.0,
  "kg": 35.274,
  "g": 0.035274,
  "mg": 0.000035274,
  "ml": 0.033814
}
```

3. **Edit the factors** (if needed for custom units):

```json
"conversion_factors_for_python": {
  "lb": 16.0,
  "kg": 35.274,
  "g": 0.035274,
  "mg": 0.000035274,
  "ml": 0.033814,
  "l": 33.814
}
```

4. **Upload the updated file** to S3 bucket **reference/** folder
5. Next processing run will use the updated conversion factors

**Important Notes:**

- Conversion only happens if unit is lb, kg, g, mg, or ml
- COUNT units are never converted (they represent discrete items like capsules, tablets)
- OZ units don't need conversion
- If size or unit is UNKNOWN, no conversion is performed

---

### Complete Output After Step 3

After Step 2 LLM extraction and Step 3 weight unit conversion (if applicable), the system has finalized data ready for the output CSV:

**Final Data Structure:**

```json
{
  "asin": "B00ABC123",
  "title": "Women's Multivitamin 50+ with Vitamin D3 60 Tablets",
  "brand": "Nature Made",
  "age": "AGE GROUP - MATURE ADULT",
  "gender": "GENDER - FEMALE",
  "form": "TABLET",
  "organic": "N/A",
  "count": "60",
  "unit": "N/A",
  "size": "1",
  "potency": "",
  "primary_ingredient": "MULTIPLE VITAMIN",
  "all_ingredients": ["MULTIPLE VITAMIN", "VITAMIN D3"],
  "category": "COMBINED MULTIVITAMINS",
  "subcategory": "WOMEN MATURE",
  "health_focus": "IMMUNE HEALTH",
  "high_level_category": "PRIORITY VMS",
  "combo_detected": false,
  "combos_applied": [],
  "reasoning": "Final classification: COMBINED MULTIVITAMINS / WOMEN MATURE | Health focus: IMMUNE HEALTH | High-level category: PRIORITY VMS"
}
```

**Key Processing Steps:**

1. **LLM extraction** (Step 2) - All attributes, ingredients, business rules, post-processing
2. **Weight unit conversion** (Step 3, if applicable) - lb/kg/g/mg/ml → OZ
3. **Result extraction** (Step 3) - Extract final values from LLM's JSON output

This finalized data is then written to the output CSV file.

---

### Audit Files & Logs Created in Step 3

**Logs:**

- `logs/{file_id}/{run_id}/step3_postprocess.log` - Log of result extraction and weight unit conversion
  - Extraction of LLM post-processing results
  - Weight unit conversions (if applicable)
  - Warnings for missing or invalid values

**Example log entries:**

```
[2025-01-08T10:35:20.123Z] [ASIN123] Post-processing complete from LLM
[2025-01-08T10:35:20.234Z] [ASIN123] Category: COMBINED MULTIVITAMINS, Subcategory: WOMEN MATURE
[2025-01-08T10:35:20.345Z] [ASIN123] Health Focus: IMMUNE HEALTH
[2025-01-08T10:35:20.456Z] [ASIN123] High-Level Category: PRIORITY VMS
[2025-01-08T10:35:20.567Z] [ASIN123] COMPLETE in 2.45s
```

**No separate audit files for Step 3** - all processing results are included in Step 2's audit JSON (`audit/step2_llm/{asin}.json`) and the final output CSV.

---

## Reference Data Files Overview

The system uses **18 reference data files** stored in the `reference_data/` folder. These files control the behavior of the LLM extraction and post-processing logic.

### All Reference Files (18 Total)

| # | File Name | Type | Used In | Purpose |
|---|-----------|------|---------|---------|
| 1 | `amazon_subcategory_lookup.csv` | CSV | Step 1 | Maps Amazon subcategories to actions (REMOVE, REMAP, UNKNOWN) |
| 2 | `non_supplement_keywords.csv` | CSV | Step 1, Step 2 (LLM) | Non-supplement keywords for filtering (with variations & exceptions) |
| 3 | `general_instructions.json` | JSON | Step 2 (LLM) | General prompt templates (output format, workflow, warnings) |
| 4 | `safety_check_instructions.json` | JSON | Step 2 (LLM) | Safety check template with supplement vs non-supplement examples |
| 5 | `age_extraction_rules.json` | JSON | Step 2 (LLM) | Rules for extracting target age group |
| 6 | `gender_extraction_rules.json` | JSON | Step 2 (LLM) | Rules for extracting target gender |
| 7 | `form_extraction_rules.json` | JSON | Step 2 (LLM) | Rules for extracting physical form (capsule, tablet, etc.) |
| 8 | `form_priority_rules.json` | JSON | Step 2 (LLM) | Priority rules when multiple forms detected |
| 9 | `organic_extraction_rules.json` | JSON | Step 2 (LLM) | Rules for determining organic status |
| 10 | `pack_count_extraction_rules.json` | JSON | Step 2 (LLM) | Rules for extracting pack count |
| 11 | `unit_extraction_rules.json` | JSON | Step 2 (LLM), Step 3 | Rules for extracting unit + conversion factors for Python |
| 12 | `size_extraction_rules.json` | JSON | Step 2 (LLM) | Rules for extracting product size (quantity per unit) |
| 13 | `ingredient_extraction_rules.json` | JSON | Step 2 (LLM) | Rules for extracting ingredients (critical rules, exclusions, combos, context-dependent) |
| 14 | `ingredient_category_lookup.csv` | CSV | Step 2 (LLM tool) | Database of 920+ ingredients with category/subcategory mappings |
| 15 | `potency_extraction_rules.json` | JSON | Step 2 (LLM) | Rules for extracting dosage/strength |
| 16 | `business_rules.json` | JSON | Step 2 (LLM tool) | 5 business rules for category/subcategory determination |
| 17 | `postprocessing_rules.json` | JSON | Step 2 (LLM tool) | Ingredient combo rules & high-level category mapping |
| 18 | `ingredient_health_focus_lookup.csv` | CSV | Step 2 (LLM tool) | Maps ingredients to health focus categories |

### File Usage by Step

**Step 1 (Non-Supplement Filtering):**
- `amazon_subcategory_lookup.csv` - Category-based filtering
- `non_supplement_keywords.csv` - Keyword-based filtering (Python regex)

**Step 2 (LLM Extraction):**
- All 16 files (JSON & CSV) - Loaded into LLM prompt and used by LLM tools
- Files #3-18 in the table above

**Step 3 (Weight Unit Conversion):**
- `unit_extraction_rules.json` - Conversion factors only

### How to Update Reference Files

**For JSON Files:**
1. Download file from S3 `reference_data/` folder
2. Edit JSON structure (add/modify/delete rules)
3. Validate JSON syntax (use https://jsonlint.com/)
4. Upload back to S3 `reference_data/` folder
5. Next processing run will use updated rules

**For CSV Files:**
1. Download file from S3 `reference_data/` folder
2. Edit in Excel or text editor
3. Maintain column structure (don't rename or remove columns)
4. Save as CSV (UTF-8 encoding)
5. Upload back to S3 `reference_data/` folder
6. Next processing run will use updated data

**Important Notes:**
- Changes take effect immediately on next processing run
- No code deployment needed
- Test changes with small batch first
- Keep backups of original files

---

## Step 4: Validation & Quality Assurance (FUTURE - POST-POC)

⚠️ **Note**: This step is **NOT YET IMPLEMENTED** and will be added after the POC (Proof of Concept) is complete and approved.

### Overview

Step 4 will add comprehensive validation and quality assurance checks to ensure the accuracy and consistency of extracted data. This step will run after Step 3 (Post-Processing) and before final output generation.

### Planned Validation Categories

#### 4.1 Data Completeness Validation

**Purpose**: Ensure all required fields are populated and no critical data is missing.

**Checks:**
- All mandatory fields have non-null values
- No UNKNOWN values in critical fields (category, subcategory, primary ingredient)
- Ingredient list is not empty (unless intentionally filtered)
- Health focus is assigned (not "HEALTH FOCUS NON-SPECIFIC" for known ingredients)

**Actions:**
- Flag products with missing critical data
- Generate warnings for incomplete extractions
- Optionally retry extraction for flagged products

#### 4.2 Data Consistency Validation

**Purpose**: Verify that extracted attributes are logically consistent with each other.

**Checks:**
- Gender matches title keywords (e.g., "Women's" → GENDER - FEMALE)
- Age group matches title keywords (e.g., "Kids" → AGE GROUP - CHILD)
- Form matches count (e.g., "60 tablets" → FORM = TABLET)
- Size and unit are compatible (e.g., SIZE = 500, UNIT = mg is valid; SIZE = 500, UNIT = COUNT is suspicious)
- Primary ingredient matches category/subcategory (e.g., CALCIUM → BASIC VITAMINS & MINERALS / MINERAL BONE & JOINT)
- Health focus aligns with primary ingredient and category

**Actions:**
- Flag inconsistencies for manual review
- Auto-correct obvious errors (if configured)
- Generate detailed inconsistency reports

#### 4.3 Business Logic Validation

**Purpose**: Ensure business rules were applied correctly and results make sense.

**Checks:**
- Multivitamin products have correct subcategory based on age/gender
- Protein products are categorized under ACTIVE NUTRITION or SPORTS NUTRITION
- Herb formulas (2+ herbs) are correctly classified as FORMULAS not SINGLES
- Ingredient combos (Glucosamine+Chondroitin, B vitamins, A+D) were detected and merged
- Prenatal products override to PRENATAL subcategory
- Weight conversions are accurate (lb → OZ, kg → OZ, etc.)

**Actions:**
- Flag products where business rules may have failed
- Re-run business rules for flagged products
- Generate business rule violation reports

#### 4.4 Range & Format Validation

**Purpose**: Ensure numeric values and text formats are within expected ranges.

**Checks:**
- Pack count is within reasonable range (1-100, typically)
- Size is within reasonable range (0.01-1000, typically)
- Potency values are formatted correctly (e.g., "1000 mg", "5000 IU")
- Age group is one of the valid values (CHILD, TEEN, ADULT, MATURE ADULT, SENIOR, NON SPECIFIC)
- Gender is one of the valid values (MALE, FEMALE, NON SPECIFIC)
- Form is one of the valid values (TABLET, CAPSULE, SOFTGEL, etc.)

**Actions:**
- Flag out-of-range values
- Validate against allowed value lists
- Generate format violation reports

#### 4.5 Duplicate Detection

**Purpose**: Identify potential duplicate products in the input data.

**Checks:**
- Same ASIN appears multiple times
- Same title + brand combination
- Same UPC (if available)
- Near-duplicate titles (fuzzy matching)

**Actions:**
- Flag duplicates for review
- Optionally deduplicate automatically
- Generate duplicate detection reports

#### 4.6 Quality Score Assignment

**Purpose**: Assign a quality score (0-100) to each product based on extraction confidence.

**Scoring Factors:**
- Number of UNKNOWN values (-10 points each)
- Number of N/A values (-5 points each)
- Ingredient lookup confidence (exact match = 100, fuzzy match = 80, low confidence = 60)
- Business rule changes applied (+10 points for successful refinement)
- Consistency checks passed (+5 points each)
- LLM extraction confidence from metadata

**Quality Tiers:**
- **Excellent (90-100)**: All fields extracted with high confidence, no issues
- **Good (75-89)**: Minor issues or low-confidence matches, likely accurate
- **Fair (60-74)**: Some UNKNOWN values or inconsistencies, review recommended
- **Poor (< 60)**: Multiple issues, manual review required

**Actions:**
- Assign quality score to each product
- Flag low-quality extractions for manual review
- Generate quality score distribution report

#### 4.7 Cross-Reference Validation

**Purpose**: Validate extracted data against external reference sources (if available).

**Checks:**
- Compare against manufacturer product catalogs
- Validate ingredient names against FDA/USDA databases
- Check brand names against known brand lists
- Verify UPC codes against product databases (if available)

**Actions:**
- Flag mismatches for review
- Auto-correct if high-confidence match found
- Generate cross-reference validation reports

### Validation Output

**Validation Report JSON:**

Each product will have a validation report attached:

```json
{
  "asin": "B00ABC123",
  "validation_status": "PASSED_WITH_WARNINGS",
  "quality_score": 85,
  "quality_tier": "Good",
  "issues": [
    {
      "type": "consistency",
      "severity": "warning",
      "field": "gender",
      "message": "Title contains 'Women's' but gender is GENDER - NON SPECIFIC",
      "suggestion": "Change gender to GENDER - FEMALE"
    },
    {
      "type": "range",
      "severity": "info",
      "field": "pack_count",
      "message": "Pack count is 1 (default value, may not be explicitly stated)",
      "suggestion": "Verify pack count is actually 1"
    }
  ],
  "checks_passed": 12,
  "checks_failed": 0,
  "checks_warned": 2,
  "validation_time_sec": 0.15
}
```

**Validation Summary CSV:**

A separate CSV file will be generated with validation results:

| ASIN | Quality Score | Quality Tier | Status | Issues Count | Primary Issue | Recommendation |
|------|--------------|-------------|--------|-------------|--------------|----------------|
| B00ABC123 | 85 | Good | PASSED_WITH_WARNINGS | 2 | Gender inconsistency | Review gender field |
| B00DEF456 | 95 | Excellent | PASSED | 0 | None | No action needed |
| B00GHI789 | 55 | Poor | FAILED | 5 | Multiple UNKNOWN values | Manual review required |

### Configuration

Validation will be configurable via `reference_data/validation_rules.json`:

```json
{
  "validation_config": {
    "enabled": true,
    "fail_on_critical_errors": false,
    "quality_score_threshold": 60,
    "auto_correct_enabled": false
  },
  "completeness_checks": {
    "required_fields": ["category", "subcategory", "primary_ingredient", "form", "age", "gender"],
    "critical_fields": ["category", "primary_ingredient"]
  },
  "range_checks": {
    "pack_count": {"min": 1, "max": 100},
    "size": {"min": 0.01, "max": 10000}
  },
  "consistency_checks": {
    "enabled": true,
    "gender_title_keywords": true,
    "age_title_keywords": true,
    "form_count_match": true
  }
}
```

### Implementation Timeline

**Phase 1 (Post-POC):**
- Data completeness validation
- Range & format validation
- Quality score assignment

**Phase 2 (Future Enhancement):**
- Data consistency validation
- Business logic validation
- Duplicate detection

**Phase 3 (Advanced Features):**
- Cross-reference validation
- Auto-correction capabilities
- ML-based anomaly detection

### Benefits

✅ **Improved Accuracy**: Catch extraction errors before they reach production  
✅ **Quality Visibility**: Know which products need manual review  
✅ **Faster Issue Resolution**: Identify and fix problems automatically  
✅ **Audit Trail**: Complete validation history for compliance  
✅ **Confidence Metrics**: Quality scores help prioritize manual review efforts  

---

