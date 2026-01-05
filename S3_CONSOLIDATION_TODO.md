# S3 Bucket Consolidation - Code Changes Needed

## Summary
Consolidated from 4 buckets to 1 bucket with folders:
- OLD: input_bucket, output_bucket, audit_bucket, reference_bucket  
- NEW: S3_BUCKET with folders (input/, output/, audit/, logs/, reference/)

## Files That Need Updates:

### 1. src/main.py (AWS mode - lines 650-800)

**OLD Environment Variables:**
```python
INPUT_BUCKET = os.getenv('INPUT_BUCKET')
OUTPUT_BUCKET = os.getenv('OUTPUT_BUCKET')
AUDIT_BUCKET = os.getenv('AUDIT_BUCKET')
```

**NEW Environment Variables:**
```python
S3_BUCKET = os.getenv('S3_BUCKET')
INPUT_PREFIX = os.getenv('INPUT_PREFIX', 'input/')
OUTPUT_PREFIX = os.getenv('OUTPUT_PREFIX', 'output/')
AUDIT_PREFIX = os.getenv('AUDIT_PREFIX', 'audit/')
LOGS_PREFIX = os.getenv('LOGS_PREFIX', 'logs/')
REFERENCE_PREFIX = os.getenv('REFERENCE_PREFIX', 'reference/')
```

**Update S3 paths:**
- s3://INPUT_BUCKET/file.csv → s3://S3_BUCKET/input/file.csv
- s3://OUTPUT_BUCKET/runs/... → s3://S3_BUCKET/output/runs/...
- s3://AUDIT_BUCKET/runs/... → s3://S3_BUCKET/audit/runs/...  
- s3://AUDIT_BUCKET/logs/... → s3://S3_BUCKET/logs/runs/...

### 2. infrastructure/upload_reference_data.sh

**OLD:**
```bash
aws s3 sync reference_data/ s3://$REFERENCE_BUCKET/
```

**NEW:**
```bash
aws s3 sync reference_data/ s3://$S3_BUCKET/reference/
```

### 3. infrastructure/deploy.sh

**OLD:**
```bash
INPUT_BUCKET=$(terraform output -raw input_bucket_name)
OUTPUT_BUCKET=$(terraform output -raw output_bucket_name)
REFERENCE_BUCKET=$(terraform output -raw reference_bucket_name)
```

**NEW:**
```bash
S3_BUCKET=$(terraform output -raw s3_bucket_name)
```

---

## Terraform Changes (DONE ✅):
- ✅ Single bucket created
- ✅ IAM policies updated
- ✅ Environment variables updated
- ✅ Outputs changed

## Application Changes (TODO):
- ❌ src/main.py AWS mode
- ❌ infrastructure/upload_reference_data.sh
- ❌ infrastructure/deploy.sh

