# AWS Deployment Guide

## Infrastructure (Already Deployed)

The Terraform infrastructure is already set up in `us-east-2`:

- **S3 Buckets:**
  - Input: `bedrock-ai-data-enrichment-input-081671069810`
  - Output: `bedrock-ai-data-enrichment-output-081671069810`
  - Audit: `bedrock-ai-data-enrichment-audit-081671069810`

- **DynamoDB Table:** `bedrock-ai-data-enrichment-processing-state`
- **IAM Role:** `bedrock-ai-data-enrichment-app-role`

## Deployment Options

### Option 1: Docker Container (ECS/EC2)

1. **Build Docker image:**
```bash
docker build -t bedrock-classifier .
```

2. **Tag for ECR:**
```bash
aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin 081671069810.dkr.ecr.us-east-2.amazonaws.com
docker tag bedrock-classifier:latest 081671069810.dkr.ecr.us-east-2.amazonaws.com/bedrock-classifier:latest
```

3. **Push to ECR:**
```bash
docker push 081671069810.dkr.ecr.us-east-2.amazonaws.com/bedrock-classifier:latest
```

4. **Run on EC2/ECS:**
```bash
docker run \
  -e AWS_REGION=us-east-2 \
  -e INPUT_BUCKET=bedrock-ai-data-enrichment-input-081671069810 \
  -e OUTPUT_BUCKET=bedrock-ai-data-enrichment-output-081671069810 \
  -e AUDIT_BUCKET=bedrock-ai-data-enrichment-audit-081671069810 \
  -e DYNAMODB_TABLE=bedrock-ai-data-enrichment-processing-state \
  -e OPENAI_API_KEY=your-key-here \
  bedrock-classifier:latest \
  python src/main_aws.py sample_10_test.csv run-001
```

### Option 2: Lambda (For Small Batches)

Lambda has limitations (15 min timeout, 10GB memory max), so best for small batches.

1. **Package code:**
```bash
./infrastructure/package_lambda.sh
```

2. **Deploy Lambda function**
3. **Trigger from S3 upload event**

### Option 3: Local Testing with AWS Integration

Test locally while reading/writing from/to AWS:

```bash
# Set AWS credentials
export AWS_PROFILE=your-profile
export OPENAI_API_KEY=your-key

# Run
python src/main_aws.py sample_10_test.csv test-run-1
```

## File Structure

```
src/
├── aws/
│   ├── s3_manager.py         # S3 operations
│   ├── dynamodb_manager.py   # State tracking
│   └── __init__.py
├── main_aws.py               # AWS cloud entry point
└── main.py                   # Local entry point
```

## Environment Variables

- `INPUT_BUCKET`: S3 bucket for input CSVs
- `OUTPUT_BUCKET`: S3 bucket for coded outputs
- `AUDIT_BUCKET`: S3 bucket for audit logs
- `DYNAMODB_TABLE`: DynamoDB table for state tracking
- `AWS_REGION`: AWS region (default: us-east-2)
- `OPENAI_API_KEY`: OpenAI API key

## Testing

1. **Upload sample file to S3:**
```bash
aws s3 cp data/input/sample_10_test.csv s3://bedrock-ai-data-enrichment-input-081671069810/
```

2. **Run processing:**
```bash
python src/main_aws.py sample_10_test.csv test-run-1
```

3. **Check results:**
```bash
aws s3 ls s3://bedrock-ai-data-enrichment-output-081671069810/runs/test-run-1/
aws s3 cp s3://bedrock-ai-data-enrichment-output-081671069810/runs/test-run-1/sample_10_test_coded.csv .
```

4. **Check DynamoDB:**
```bash
aws dynamodb query \
  --table-name bedrock-ai-data-enrichment-processing-state \
  --index-name StatusIndex \
  --key-condition-expression "status = :status" \
  --expression-attribute-values '{":status":{"S":"success"}}'
```

## Permissions Required

The IAM role needs:
- S3: GetObject, PutObject, ListBucket on all 3 buckets
- DynamoDB: GetItem, PutItem, UpdateItem, Query on the table
- CloudWatch Logs: CreateLogGroup, CreateLogStream, PutLogEvents

## Cost Estimation

For 10,000 products:
- **OpenAI API**: ~$50-100 (depends on gpt-5-mini pricing)
- **S3**: < $1 (storage + requests)
- **DynamoDB**: < $1 (on-demand pricing)
- **ECS/EC2**: ~$5-20 (depends on instance size and runtime)

**Total**: ~$56-122 for 10K products

## Next Steps

1. ✅ Infrastructure deployed
2. ✅ Docker image created
3. ✅ AWS integration modules built
4. 🔄 Upload sample data to S3
5. 🔄 Test end-to-end
6. 🔄 Create Lambda handler (optional)
7. 🔄 Set up CI/CD pipeline

