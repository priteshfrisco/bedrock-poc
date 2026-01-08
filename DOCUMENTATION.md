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

**Our New LLM-Based System (All 15+ columns extracted automatically):**

Our system extracts ALL columns automatically in one pass using GPT-5-mini with tool calling, eliminating the need for most manual work:

| Column | Extraction Method | R System Equivalent |
|--------|------------------|---------------------|
| `RetailerSku` | From input (ASIN) | Same |
| `UPC` | Empty (manual lookup still required) | Same (manually added) |
| `Description` | From input (title) | Title |
| `Brand` | From input | Same |
| **`NW Category`** | **LLM + tool calling + business rules** | Category (ML model) |
| **`NW Subcategory`** | **LLM + tool calling + business rules** | Subcategory (ML model) |
| `NW Sub Brand 1, 2, 3` | Empty (manual entry for NW/IT) | Same (manually added) |
| **`Potency`** | **LLM extraction (Step 9)** | **Manually added by analysts** ✨ NEW! |
| **`FORM`** | **LLM extraction (Step 3)** | Form (Random Forest ML) |
| **`AGE`** | **LLM extraction (Step 1)** | Age (Random Forest ML) |
| **`GENDER`** | **LLM extraction (Step 2)** | Gender (Random Forest ML) |
| `COMPANY` | Default to brand (manual refinement) | Same (manually added) |
| **`FUNCTIONAL INGREDIENT`** | **LLM + tool calling (Step 8)** | Functional Ingredient (rule-based) |
| **`HEALTH FOCUS`** | **Lookup via primary ingredient** | Health Focus (XGBoost ML) |
| **`SIZE`** | **LLM extraction (Step 7) + conversion** | Size/Count (regex patterns) |
| **`HIGH LEVEL CATEGORY`** | **Rule-based assignment** | Same |
| `NW_UPC` | Empty (NW/IT internal only) | Same (manually added) |
| **`Unit of Measure`** | **LLM extraction (Step 6) + conversion** | Unit (regex patterns) |
| **`Pack Count`** | **LLM extraction (Step 5)** | **Manually verified** ✨ NEW! |
| **`Organic`** | **LLM extraction (Step 4)** | Organic (keyword detection) |
| **`Reasoning`** | **Auto-generated from business rules** | Manual notes |

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

1. `age_extraction_rules.json` - Rules for extracting target age group
2. `gender_extraction_rules.json` - Rules for extracting target gender
3. `form_extraction_rules.json` - Rules for extracting physical form (capsule, tablet, etc.)
4. `form_priority_rules.json` - Priority rules when multiple forms are detected
5. `organic_extraction_rules.json` - Rules for determining organic status
6. `size_extraction_rules.json` - Rules for extracting quantity per unit
7. `unit_extraction_rules.json` - Rules for extracting unit of measurement
8. `pack_count_extraction_rules.json` - Rules for extracting pack size
9. `potency_extraction_rules.json` - Rules for extracting dosage/strength
10. `ingredient_extraction_rules.json` - Rules for extracting functional ingredients
11. `ingredient_category_lookup.csv` - Database of ingredients with categories (used by `lookup_ingredient` tool)
12. `business_rules.json` - Business rules for category/subcategory assignment (used by `apply_business_rules` tool)
13. `non_supplement_keywords.csv` - Safety check keywords grouped by category
14. `safety_check_instructions.json` - Safety check template with examples of supplements vs non-supplements

### Audit Files Created in Step 2

For each product processed:

- `audit/step2_llm/{asin}.json` - Complete extraction result including all attributes, ingredients, business rules applied, token usage, and API cost

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

| Product Title                                      | Extracted Gender      | Reasoning                                |
|----------------------------------------------------|-----------------------|------------------------------------------|
| Men's Daily Multivitamin 60 Tablets               | GENDER - MALE         | Contains "men's"                         |
| Women's 50+ Multivitamin                          | GENDER - FEMALE       | Contains "women's"                       |
| Prostate Support Formula 90 Capsules              | GENDER - MALE         | Contains "prostate" (male-specific)      |
| Prenatal DHA Omega-3 Softgels                     | GENDER - FEMALE       | Contains "prenatal" (female-specific)    |
| Vitamin D3 5000 IU Softgels                       | GENDER - NON SPECIFIC | No gender keyword found                  |

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

| Product Title                                      | Extracted Form         | Reasoning                                      |
|----------------------------------------------------|------------------------|------------------------------------------------|
| Vitamin D3 5000 IU Softgels 100 Count             | SOFTGEL                | Contains "softgels"                            |
| Turmeric Powder in Vegetable Capsules             | VEGETABLE CAPSULE      | Priority rule: powder IN capsules = capsule    |
| Kids Chewable Multivitamin Gummies                | GUMMY                  | Contains "gummies"                             |
| Elderberry Cough Drops 30 Count                   | LOZENGE                | Priority rule: cough drops = lozenge           |
| Protein Powder Chocolate 2lb                      | POWDER                 | Contains "powder"                              |

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

| Product Title | Keywords Found | Result | Reasoning |
|---------------|----------------|--------|-----------|
| "Nature Made Organic Turmeric 500mg" | "organic" | ORGANIC | Contains organic keyword |
| "Garden of Life Vitamin D3 60 Capsules" | none | NOT ORGANIC | No organic keywords (default) |
| "Supplement with organic and inorganic minerals" | "organic", "inorganic" | NOT ORGANIC | Priority 1 rule (inorganic) takes precedence |
| "USDA Certified Organic Ashwagandha" | "usda organic", "certified organic" | ORGANIC | Contains organic certification keywords |

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

| Product Title | Size Extracted | Reasoning |
|--------------|----------------|-----------|
| "Fish Oil 1000mg 180 Softgels" | 180 | Found "180 softgels" (NOT 1000, which is dosage) |
| "Vitamin D 5000 IU 60 Capsules" | 60 | Found "60 capsules" (NOT 5000, which is dosage in IU) |
| "Elderberry Syrup 8 fl oz" | 8 | Found "8 fl oz" (volume measurement) |
| "Whey Protein Powder 2 lbs" | 2 | Found "2 lbs" (weight measurement) |
| "Creatine Monohydrate 500 g" | 500 | Found "500 g" (weight in grams) |
| "CoQ10 100mg 60 Capsules" | 60 | Size is 60 (NOT 100, which is dosage, NOT 10 from CoQ10) |
| "Multivitamin Gummy" | UNKNOWN | No size information found in title |

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

| Product Title | Unit Extracted | Reasoning |
|--------------|----------------|-----------|
| "Fish Oil 1000mg 180 Softgels" | COUNT | Discrete units "softgels" found → return COUNT |
| "Vitamin D 60 Capsules" | COUNT | Discrete units "capsules" found → return COUNT |
| "Elderberry Syrup 8 fl oz" | oz | Volume unit "fl oz" found → return "oz" |
| "Whey Protein Powder 2 lbs" | lb | Weight unit "lbs" found → return base form "lb" |
| "Creatine Monohydrate 500 g" | g | Weight unit "g" found → return "g" |
| "Vitamin C Powder 1 kg" | kg | Weight unit "kg" found → return "kg" |
| "Multivitamin Gummy" | UNKNOWN | No unit found → return UNKNOWN |

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

| Product Title | Pack Count | Reasoning |
|--------------|------------|-----------|
| "2 Pack Fish Oil 180 Capsules" | 2 | Found "2 pack" (NOT 180, which is size) |
| "Pack of 3 Vitamin D 5000 IU" | 3 | Found "pack of 3" |
| "4 Bottles Vitamin C 500mg" | 4 | Found "4 bottles" |
| "Multivitamin 60 Tablets" | 1 | No pack keyword found → default to 1 |
| "Elderberry Syrup 8 fl oz" | 1 | No pack keyword found → default to 1 |
| "Case of 6 Protein Bars" | 6 | Found "case of 6" |

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

| Column | Description |
|--------|-------------|
| `INGREDIENT` | Normalized ingredient name (e.g., "VITAMIN C (NOT ESTER-C)", "PROBIOTIC SUPPLEMENT") |
| `NW_CATEGORY` | Nature's Way category assignment |
| `NW_SUBCATEGORY` | Nature's Way subcategory assignment |

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

**⚙️ Advanced R System Features (Post-Processing in Step 3)**

After the LLM extracts ingredients in Step 8, our Step 3 post-processing applies three advanced features matching the original R system:

**Feature 1: Ingredient Combo Detection**

Automatically merges specific ingredient combinations (matching R system's FinalMerge.R logic):

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
- Location: `src/pipeline/step3_postprocess.py` → `detect_ingredient_combos()`
- Rules defined in: `reference_data/ingredient_extraction_rules.json` → `combo_detection` section
- Applied automatically in Step 3 before business rules

---

**Feature 2: Granular Protein Type Detection**

Automatically detects specific protein types with 200+ lines of logic matching R system's FI_CAT_Testing.R:

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

| Product Title | Detected Type | Logic |
|--------------|---------------|-------|
| "Whey Protein Isolate 2 lbs" | PROTEIN - ANIMAL - WHEY | Single animal keyword |
| "Pea Protein Powder Vegan" | PROTEIN - PLANT - PEA | Single plant keyword |
| "Whey Casein Blend 5 lbs" | PROTEIN - ANIMAL - WHEY & CASEIN | Common animal pair |
| "Pea Rice Protein Organic" | PROTEIN - PLANT - MULTI | Multiple plant keywords |
| "Whey Pea Protein Blend" | PROTEIN - ANIMAL & PLANT COMBO | Both plant and animal |

**Implementation:**
- Location: `src/pipeline/utils/business_rules.py` → `detect_granular_protein_type()`
- Applied in Step 3 when primary ingredient is protein
- Overrides subcategory with granular type

---

**Feature 3: Context-Dependent Ingredients**

Some ingredients require context to identify correctly (matching R system special case logic):

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
- Location: `reference_data/ingredient_extraction_rules.json` → `context_dependent_ingredients` section
- The LLM checks these rules BEFORE calling `lookup_ingredient()` tool
- Ensures correct ingredient is looked up based on context

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

| INGREDIENT | NW_CATEGORY | NW_SUBCATEGORY |
|------------|-------------|----------------|
| ASHWAGANDHA | HERBS | SINGLES |
| VITAMIN C (NOT ESTER-C) | LETTER VITAMINS | VITAMIN C |

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

| Product Title | Primary Ingredient | Potency | Reasoning |
|--------------|-------------------|---------|-----------|
| "Probiotic 50 Billion CFU 30 Capsules" | probiotic | 50 | Numeric value only |
| "Vitamin D3 5000 IU 120 Softgels" | vitamin d3 | 5000 IU | Primary ingredient potency |
| "Turmeric 500mg with Black Pepper 60 Capsules" | turmeric | 500mg | Primary is 500mg |
| "Fish Oil 1000mg (EPA 180mg DHA 120mg) 180 Softgels" | fish oil | 1000mg | Total is 1000mg (EPA/DHA are components) |
| "Magnesium 200mg with Vitamin B6 25mg 90 Capsules" | magnesium | 200mg | Primary is 200mg, B6 secondary |
| "Multivitamin for Women 60 Tablets" | multivitamin | (empty) | No single potency (mix of nutrients) |
| "Ultimate Flora Probiotic 100B 30 Capsules" | probiotic | 100 | 100B = 100 billion, numeric only |

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
