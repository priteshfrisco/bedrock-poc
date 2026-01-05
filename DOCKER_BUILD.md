# Docker Image Build Guide

## Quick Start

### 1. Build Docker Image

```bash
cd /Users/priteshfrisco/Desktop/bedrock-poc
docker build -t bedrock-ai-pipeline:latest .
```

**Expected output:** "Successfully built..." and "Successfully tagged bedrock-ai-pipeline:latest"

---

### 2. Test Locally

Test the unified main.py with local mode:

```bash
docker run --rm \
  -v $(pwd)/data:/app/data \
  -e OPENAI_API_KEY="your-key-here" \
  bedrock-ai-pipeline:latest \
  python src/main.py --mode local
```

---

### 3. Test AWS Mode (without S3)

Test AWS mode locally (will fail on S3 but validates the command):

```bash
docker run --rm \
  -e OPENAI_API_KEY="your-key-here" \
  -e INPUT_BUCKET="test-bucket" \
  -e INPUT_KEY="test.csv" \
  -e OUTPUT_BUCKET="test-output" \
  -e AUDIT_BUCKET="test-audit" \
  -e DYNAMODB_TABLE="test-table" \
  bedrock-ai-pipeline:latest
```

---

### 4. Push to AWS ECR

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 081671069810.dkr.ecr.us-east-1.amazonaws.com

# Tag image
docker tag bedrock-ai-pipeline:latest 081671069810.dkr.ecr.us-east-1.amazonaws.com/bedrock-ai-data-enrichment:latest

# Push to ECR
docker push 081671069810.dkr.ecr.us-east-1.amazonaws.com/bedrock-ai-data-enrichment:latest
```

---

## Unified main.py Architecture

**Single Entry Point:** `src/main.py`

### Local Mode (Default)
```bash
python src/main.py
# or
python src/main.py --mode local
```
- Reads from `data/input/`
- Writes to `data/output/`
- Uses local file system

### AWS Mode
```bash
python src/main.py --mode aws \
  --input-bucket BUCKET \
  --input-key FILE \
  --output-bucket BUCKET \
  --audit-bucket BUCKET \
  --dynamodb-table TABLE \
  --sns-topic-arn ARN
```
- Reads from S3
- Writes to S3
- Tracks state in DynamoDB
- Sends SNS notifications

---

## Docker Configuration

### Dockerfile Default
```dockerfile
CMD ["python", "src/main.py", "--mode", "aws"]
```

The container runs in **AWS mode by default** (for ECS deployment).

### Override for Local Testing
```bash
docker run ... bedrock-ai-pipeline:latest python src/main.py --mode local
```

---

## AWS Deployment Flow

1. **S3 Upload** → Triggers Lambda
2. **Lambda** → Starts ECS Fargate Task with:
   ```python
   command: ['python', 'src/main.py', '--mode', 'aws', '--input-key', key, '--run-id', run_id]
   ```
3. **ECS Task** → Processes file, writes to S3, tracks in DynamoDB
4. **SNS** → Sends email notification on completion/failure

---

## Benefits of Unified Approach

✅ **Single Source of Truth** - No duplicate code  
✅ **Easy Testing** - Just change `--mode` flag  
✅ **Professional CLI** - Clear arguments  
✅ **Conditional Imports** - boto3 only loaded in AWS mode  
✅ **Environment Fallbacks** - Args or ENV variables  

---

## Troubleshooting

### Docker not running?
```bash
# On macOS
open -a Docker

# Wait for Docker Desktop to start, then retry build
```

### Image size too large?
```bash
# Check image size
docker images bedrock-ai-pipeline:latest

# Should be ~500MB-1GB with Python 3.13-slim
```

### Testing without AWS?
```bash
# Local mode doesn't require AWS credentials
python src/main.py --mode local
```

---

## Next Steps

After building the Docker image:

1. ✅ Test locally with `--mode local`
2. ✅ Push to ECR with `infrastructure/deploy_docker.sh`
3. ✅ Deploy infrastructure with `infrastructure/deploy.sh`
4. ✅ Upload test file to S3 input bucket
5. ✅ Watch CloudWatch logs for processing
6. ✅ Check S3 output bucket for results

---

**Ready to deploy!** 🚀

