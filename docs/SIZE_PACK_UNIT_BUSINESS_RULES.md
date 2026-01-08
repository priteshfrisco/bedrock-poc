# Size, Pack, and Unit Conversion - R System Business Rules

## Overview
This document details the business rules from the R system for handling SIZE (pack count), COUNT (quantity), and UNIT (measurement) extraction and conversion.

---

## 1. PACK SIZE (from `Pack Size Final.R`)

### Purpose
Extract the number of packages/bottles in the product (NOT the number of capsules/tablets).

### Pattern Matching
**Regex Pattern:**
```regex
((\\d{1,3}\\s*(pk|pks|pack|packs|package|packages|bottle|bottles)(?!\\w))|(pack of|case of|)\\s*\\d{1,3})
```

### Keywords
- `pk`, `pks`
- `pack`, `packs`
- `package`, `packages`
- `bottle`, `bottles`
- `pack of [NUMBER]`
- `case of [NUMBER]`

### Business Rules
1. **Extract numeric part** from the pattern match
2. **Default to 1** if no pack keywords found (`pack_final[is.na(pack_final)] <- 1`)
3. **Do NOT confuse** with count (capsules/tablets)

### Examples
| Title | Pack Size | Reasoning |
|-------|-----------|-----------|
| "2 Pack Fish Oil 180 Capsules" | 2 | Found "2 Pack" |
| "Pack of 3 Vitamin D" | 3 | Found "pack of 3" |
| "Multivitamin 60 Tablets" | 1 | No pack keyword → default to 1 |
| "4 Bottles Vitamin C 500mg" | 4 | Found "4 bottles" |

### Output Column
- **Size** (numeric): Pack count

---

## 2. COUNT & UNIT (from `Count Size Coding Final lb update.R`)

### Purpose
Extract the QUANTITY and UNIT OF MEASUREMENT from product title. This is a **TWO-STEP** process:
1. Extract count and identify if it's discrete (COUNT) or weight/volume (OZ, lb, g, kg, ml)
2. Convert all weight/volume units to OZ for standardization

---

### STEP 1: Pattern Matching & Initial Classification

#### Count Pattern (Regex)
```regex
(((\\d{1,4}|(\\d{1,2}\\.\\d{1,2})|(\\.\\d{1,2}))\\s*(count|ct|ct.|caps|vcaps|
vegcaps|veggie caps|vegetable caps|veg capsules|caplet|caps|pcs|strips|cap|drcaps|veg drcaps|veg caps|chewable|gummy|tabs|tab|gummies|sg|sgels|
soft chews|liquid softgels|packet|packets|box|bags|tea bags|capsules|veggie capsules|capsule|chew tabs|chewable tablets|tablets|tablet|pill|piece|throat drops|cough drops|drops|
veg. cap|fl ozs|fluid ozs|fluid oz|fluid ounce|fl oz|fl. oz|fl.oz|oz|fl ounces|ounces|ounce|chwbls|chewable gummies|vegetarian capsules|vegicaps|ea|each|lozenges|lozenge|
sachets|sachet|serving|vtab|beadlet|vegan cap|vegetarian caps|vegan tab|sprays|mini softgels|liquid soft gels|softgels|soft gels|soft gel|softgel|liquidgels|pellets|pellet|vegan friendly capsules|wafers|rapid release softgel|gelatin capsule|quick dissolve tablet|per pack))|\\d{1,3}(ct.|ct|oz\\s*|oz.|count|cap|ea|each))
```

#### Count Keywords (Discrete Units → "COUNT")
```
count, ct, ct., caps, vcaps, vegcaps, veggie caps, vegetable caps, veg capsules,
caplet, caps, pcs, strips, cap, drcaps, veg drcaps, veg caps, chewable, gummy,
tablet, tabs, tab, gummies, sg, sgels, soft chews, liquid softgels, packet, packets,
box, bags, tea bags, capsules, veggie capsules, capsule, chew tabs, chewable tablets,
tablets, tablet, pill, piece, throat drops, cough drops, drops, veg. cap, chwbls,
chewable gummies, vegetarian capsules, vegicaps, ea, each, lozenges, lozenge,
sachets, sachet, serving, vtab, beadlet, vegan cap, vegetarian caps, vegan tab,
sprays, mini softgels, liquid soft gels, softgels, soft gels, soft gel, softgel,
liquidgels, pellets, pellet, vegan friendly capsules, wafers, rapid release softgel,
gelatin capsule, quick dissolve tablet, per pack
```

#### Volume/Weight Keywords
- **OZ**: `ounces`, `ounce`, `oz`, `fl oz`, `fl. oz`, `fl.oz`, `fluid oz`, `fluid ounce`, `fl ounces`
- **LB**: `lb`, `lbs`, `pound`, `pounds`
- **KG**: `kg`, `kgs`, `kilo`, `kilos`, `kilogram`, `kilograms`
- **G**: `g`, `gm`, `gram`, `grams`
- **MG**: `mg`, `milligram`, `milligrams`
- **ML**: `ml`, `millil`, `milliliter`, `milliliters`

---

### STEP 2: Unit Classification Logic

#### R Code Logic (Lines 82-90)
```r
for(i in 1:nrow(count_final)){
  if(grepl("ounces|ounce|oz", count_final$Count[i])){
    count_final$Count[i] <- "OZ"
  } else if(is.na(count_final$Count[i])) {
    count_final$Count[i] <- "UNKNOWN"
  } else{
    count_final$Count[i] <- "COUNT"
  }
}
```

**Business Rules:**
1. If unit contains `ounces|ounce|oz` → Set unit to **"OZ"**
2. If unit is missing/NA → Set unit to **"UNKNOWN"**
3. Otherwise (discrete units) → Set unit to **"COUNT"**

---

### STEP 3: Handling UNKNOWN Cases

#### Alternative Pattern (Lines 112)
For products with UNKNOWN count/unit, search for:
```regex
(((\\d{1,4})|(\\d{1,2}\\.\\d{1,2})|(\\.\\d{1,2}))\\s*(lb|pounds|lbs|pound|kilo|kg|kgs|kilos|kilograms|mg|g|ml|millil))
```

#### Fallback Logic (Lines 127-148)
If still UNKNOWN, loop through count keywords and:
1. Find keyword in title
2. Search backwards (30 chars before keyword) for a number
3. Skip if number has `%` symbol
4. Extract numeric value
5. Set unit to "COUNT"

---

### STEP 4: Unit Conversion to OZ

#### R Code Logic (Lines 156-177)
**Convert all weight/volume units to OZ:**

```r
for(i in 1:nrow(keep_looking2)) {
  if(!is.na(keep_looking2$Count[i])){
    if (keep_looking2$Count[i] == "lb" || keep_looking2$Count[i] == "lbs" || 
        keep_looking2$Count[i] == "pound"|| keep_looking2$Count[i] == "pounds") {
      keep_looking2$Count_numeric[i]=keep_looking2$Count_numeric[i]*16
    }else if(keep_looking2$Count[i] == "g"){
      keep_looking2$Count_numeric[i]=keep_looking2$Count_numeric[i]*0.035274
    }else if(keep_looking2$Count[i] == "mg"){
      keep_looking2$Count_numeric[i]=keep_looking2$Count_numeric[i]*0.000035274
    }else if(keep_looking2$Count[i] == "kg" || keep_looking2$Count[i] == "kgs" || 
             keep_looking2$Count[i] == "kilos" || keep_looking2$Count[i] == "kilogram" || 
             keep_looking2$Count[i] == "kilograms"){
      keep_looking2$Count_numeric[i]=keep_looking2$Count_numeric[i]*35.274
    }else if(keep_looking2$Count[i] == "ml" ||keep_looking2$Count[i] == "millil" ){
      keep_looking2$Count_numeric[i]=keep_looking2$Count_numeric[i]*0.033814
    }
    if(keep_looking2$Count[i] != "COUNT"){
      keep_looking2$Count[i]='OZ'
    }
  }
}
```

#### Conversion Factors (Weight/Volume → OZ)
| Unit | Factor | Formula |
|------|--------|---------|
| **lb** (pounds) | 16.0 | `count * 16` |
| **kg** (kilograms) | 35.274 | `count * 35.274` |
| **g** (grams) | 0.035274 | `count * 0.035274` |
| **mg** (milligrams) | 0.000035274 | `count * 0.000035274` |
| **ml** (milliliters) | 0.033814 | `count * 0.033814` |

**After conversion:**
- All weight/volume units → Unit becomes **"OZ"**
- Discrete units (capsules, tablets, etc.) → Unit remains **"COUNT"**

---

## 3. Final Output Columns

### From `Count Size Coding Final lb update.R`
| Column Name | Description | Example Values |
|-------------|-------------|----------------|
| **RetailerSku** | Product SKU | "B001..." |
| **Count** | Quantity (numeric, may be converted to OZ) | 180, 32.0, 17.637 |
| **Unit Of Measurement** | Unit type | "COUNT", "OZ", "UNKNOWN" |

### From `Pack Size Final.R`
| Column Name | Description | Example Values |
|-------------|-------------|----------------|
| **RetailerSku** | Product SKU | "B001..." |
| **Size** | Pack count | 1, 2, 3, 4 |

---

## 4. Critical Business Rules Summary

### DO's ✅
1. **Extract numeric value** before unit keywords
2. **Classify unit** as COUNT, OZ, or weight unit (lb, kg, g, mg, ml)
3. **Convert all weight/volume** units to OZ using exact conversion factors
4. **Default pack size to 1** if no pack keywords found
5. **Return "UNKNOWN"** if count/unit cannot be determined
6. **Keep COUNT units as-is** (no conversion)

### DON'Ts ❌
1. **DON'T confuse dosage** (mg, IU, mcg) with count
2. **DON'T confuse pack size** (bottles) with count (capsules)
3. **DON'T convert COUNT** to OZ (discrete units stay as COUNT)
4. **DON'T round conversions** excessively (keep precision up to 6 decimals)

---

## 5. Complete Examples

### Example 1: Discrete Units (Capsules)
**Input:** "Fish Oil 1000mg 180 Softgels"
- **Count:** 180 (found "180 softgels")
- **Unit:** COUNT (discrete unit)
- **Size:** 1 (no pack keyword)
- **Conversion:** None (COUNT stays as-is)

### Example 2: Weight Unit (Pounds)
**Input:** "Whey Protein Powder 2 lbs"
- **Count:** 2 (found "2 lbs")
- **Unit:** lb → **Convert to OZ**
- **Conversion:** 2 × 16 = **32 OZ**
- **Final Count:** 32
- **Final Unit:** OZ
- **Size:** 1 (no pack keyword)

### Example 3: Weight Unit (Grams)
**Input:** "Creatine Monohydrate 500 g"
- **Count:** 500 (found "500 g")
- **Unit:** g → **Convert to OZ**
- **Conversion:** 500 × 0.035274 = **17.637 OZ**
- **Final Count:** 17.637
- **Final Unit:** OZ
- **Size:** 1 (no pack keyword)

### Example 4: Multi-Pack with Capsules
**Input:** "2 Pack Fish Oil 180 Capsules"
- **Count:** 180 (found "180 capsules")
- **Unit:** COUNT (discrete unit)
- **Size:** 2 (found "2 pack")
- **Conversion:** None (COUNT stays as-is)

### Example 5: Volume Unit (Fluid Ounces)
**Input:** "Elderberry Syrup 8 fl oz"
- **Count:** 8 (found "8 fl oz")
- **Unit:** oz (already in OZ)
- **Final Count:** 8
- **Final Unit:** OZ
- **Size:** 1 (no pack keyword)
- **Conversion:** None (already in OZ)

### Example 6: Multi-Bottle Pack
**Input:** "3 Bottles Vitamin C 500mg 60 Tablets"
- **Count:** 60 (found "60 tablets")
- **Unit:** COUNT (discrete unit)
- **Size:** 3 (found "3 bottles")
- **Conversion:** None (COUNT stays as-is)

---

## 6. Preprocessing Steps (from R Code)

### Text Replacements (Lines 32-38)
```r
df_test_count$Title <- str_replace_all(df_test_count$Title, '1/2', ".5")
df_test_count$Title <- str_replace_all(df_test_count$Title, '\\+', "plus")
df_test_count$Title <- str_replace_all(df_test_count$Title, '\\&', "and")
df_test_count$Title <- str_replace_all(df_test_count$Title, '\\-', " ")
df_test_count$Title <- str_replace_all(df_test_count$Title, '/', " ")
df_test_count$Title <- str_replace_all(df_test_count$Title, '\\)', " ")
df_test_count$Title <- str_replace_all(df_test_count$Title, '\\(', " ")
```

**Preprocessing Rules:**
1. Replace `1/2` with `.5`
2. Replace `+` with `plus`
3. Replace `&` with `and`
4. Replace `-` with space
5. Replace `/` with space
6. Replace `(` with space
7. Replace `)` with space
8. Convert to lowercase

---

## 7. Python Implementation Status

### ✅ Currently Implemented
1. **Unit conversion logic** (`src/pipeline/utils/unit_converter.py`)
   - Conversion factors match R exactly
   - Converts lb, kg, g, mg, ml → OZ
   - Keeps COUNT as-is
2. **Reference files** (`reference_data/`)
   - `count_extraction_rules.json`
   - `unit_extraction_rules.json`
   - `size_extraction_rules.json`

### ❌ Potential Issues to Fix
1. **Pack size default**: Need to verify Python defaults to 1 when no pack found
2. **UNKNOWN handling**: Need to verify fallback logic for UNKNOWN cases
3. **Preprocessing**: Need to verify text replacements (1/2 → .5, etc.)
4. **Regex patterns**: Need to verify Python uses same comprehensive patterns as R
5. **Unit classification**: Need to verify "OZ" vs "COUNT" classification logic matches R exactly

---

## 8. Next Steps for Python Implementation

### High Priority Fixes
1. **Verify pack size default** behavior (should be 1, not UNKNOWN)
2. **Add preprocessing** text replacements to match R system
3. **Review LLM prompts** to ensure count vs dosage distinction is clear
4. **Add validation** that conversion factors exactly match R
5. **Test edge cases** from R system (fractions, multiple units, etc.)

### Testing Checklist
- [ ] Test discrete units (capsules, tablets) → COUNT
- [ ] Test weight units (lb, kg, g, mg) → OZ conversion
- [ ] Test volume units (fl oz, oz) → OZ (no conversion)
- [ ] Test pack size extraction (2 pack, 3 bottles, etc.)
- [ ] Test pack size default (no keywords → 1)
- [ ] Test UNKNOWN handling (missing count/unit)
- [ ] Test preprocessing (1/2 → .5, special chars)
- [ ] Test edge cases (dosage vs count, multi-packs)

---

## Appendix: R Code File Locations

- **Count & Unit**: `/old_r_data/Nature's Way Current Process/Amazon Coding Resources - Copy/ModelScripts/Count Size Coding Final lb update.R`
- **Pack Size**: `/old_r_data/Nature's Way Current Process/Amazon Coding Resources - Copy/ModelScripts/Pack Size Final.R`

