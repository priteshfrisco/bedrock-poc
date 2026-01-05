# AWS Deployment Checklist

## Prerequisites ✓
- [x] Infrastructure deployed via Terraform (S3, DynamoDB, IAM)
- [x] Docker image ready
- [x] AWS integration code complete

---

## What YOU Need to Do in AWS

### 1. Configure AWS Credentials & Permissions ⚙️

**Option A: Use Your Current AWS User**

Add these permissions to your IAM user/role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::bedrock-ai-data-enrichment-input-081671069810",
        "arn:aws:s3:::bedrock-ai-data-enrichment-input-081671069810/*",
        "arn:aws:s3:::bedrock-ai-data-enrichment-output-081671069810",
        "arn:aws:s3:::bedrock-ai-data-enrichment-output-081671069810/*",
        "arn:aws:s3:::bedrock-ai-data-enrichment-audit-081671069810",
        "arn:aws:s3:::bedrock-ai-data-enrichment-audit-081671069810/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-2:081671069810:table/bedrock-ai-data-enrichment-processing-state",
        "arn:aws:dynamodb:us-east-2:081671069810:table/bedrock-ai-data-enrichment-processing-state/index/*"
      ]
    }
  ]
}
```

**To add this policy:**
1. Go to AWS Console → IAM → Users → [Your User]
2. Click "Add permissions" → "Create inline policy"
3. Paste the JSON above
4. Name it: `BedrockPOC-Access`
5. Click "Create policy"

---

**Option B: Assume the IAM Role Created by Terraform**

The role `bedrock-ai-data-enrichment-app-role` already has all permissions, but you need to:

1. Update the trust policy to allow your user to assume it
2. Or attach this role to an EC2 instance and run from there

---

### 2. Quick Test (10 minutes) 🧪

Run this script to verify everything works:

```bash
cd /Users/priteshfrisco/Desktop/bedrock-poc

# Run the test script
./infrastructure/test_aws_setup.sh

# If successful, test the full pipeline
export OPENAI_API_KEY=your-key-here
PYTHONPATH=. python src/main_aws.py sample_10_test.csv test-run-1
```

**Expected result:**
- ✅ Reads CSV from S3
- ✅ Processes 10 products
- ✅ Writes results to S3
- ✅ Tracks status in DynamoDB

---

### 3. Check Results 📊

```bash
# Download output
aws s3 cp s3://bedrock-ai-data-enrichment-output-081671069810/runs/test-run-1/sample_10_test_coded.csv ./test_results.csv

# Open in Excel/Numbers
open test_results.csv

# Check DynamoDB
aws dynamodb scan \
  --table-name bedrock-ai-data-enrichment-processing-state \
  --region us-east-2 \
  --max-items 5
```

---

### 4. Production Deployment (Optional) 🚀

**For processing 1000s of records:**

#### Option A: ECS Fargate (Serverless, Auto-scaling)

1. **Create ECR repository:**
```bash
aws ecr create-repository --repository-name bedrock-classifier --region us-east-2
```

2. **Build & push Docker image:**
```bash
docker build -t bedrock-classifier .
aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin 081671069810.dkr.ecr.us-east-2.amazonaws.com
docker tag bedrock-classifier:latest 081671069810.dkr.ecr.us-east-2.amazonaws.com/bedrock-classifier:latest
docker push 081671069810.dkr.ecr.us-east-2.amazonaws.com/bedrock-classifier:latest
```

3. **Create ECS task & service** (via AWS Console or Terraform)

#### Option B: EC2 Instance (Simple)

1. Launch EC2 instance (t3.large or bigger)
2. Attach IAM role: `bedrock-ai-data-enrichment-app-role`
3. SSH and run:
```bash
# Install Docker
sudo yum install -y docker
sudo service docker start

# Pull and run
docker pull 081671069810.dkr.ecr.us-east-2.amazonaws.com/bedrock-classifier:latest
docker run -e OPENAI_API_KEY=your-key bedrock-classifier python src/main_aws.py your-file.csv run-001
```

---

## Summary

**Minimum steps to test:**

1. ✅ Add S3 + DynamoDB permissions to your IAM user (5 min)
2. ✅ Run `./infrastructure/test_aws_setup.sh` (2 min)
3. ✅ Set `OPENAI_API_KEY` and run `main_aws.py` (5-10 min)
4. ✅ Check results in S3 (1 min)

**Total time: ~15-20 minutes**

---

## Troubleshooting

**Error: "Access Denied" on S3**
→ Add S3 permissions to your IAM user (see step 1)

**Error: "ResourceNotFoundException" on DynamoDB**
→ Check you're in the correct region (us-east-2)
→ Add DynamoDB permissions to your IAM user

**Error: "No module named 'src'"**
→ Set PYTHONPATH: `PYTHONPATH=. python src/main_aws.py ...`

**Docker build fails**
→ Make sure you're in the project root directory
→ Check Docker is running

---

## Need Help?

1. Run `./infrastructure/test_aws_setup.sh` to diagnose issues
2. Check AWS CloudWatch Logs for detailed error messages
3. Verify IAM permissions in AWS Console

