# Docker & ECR Setup Guide

## What You Need to Create

### Option 1: Test WITHOUT Docker (Quickest - 5 min) ✅

You can test the AWS integration **right now without Docker**:

```bash
cd /Users/priteshfrisco/Desktop/bedrock-poc
export AWS_PROFILE=ai-data-enrichment
export OPENAI_API_KEY=sk-your-key

# Run directly with Python
PYTHONPATH=. python src/main_aws.py sample_10_test.csv test-run-1
```

**This is the fastest way to verify everything works!**

---

### Option 2: Create Docker Image & Push to ECR (15 min)

Once you've verified it works with Option 1, create the Docker infrastructure:

#### Step 1: Run the deployment script

```bash
cd /Users/priteshfrisco/Desktop/bedrock-poc
export AWS_PROFILE=ai-data-enrichment

# This will:
# 1. Create ECR repository
# 2. Build Docker image
# 3. Push to ECR
./infrastructure/deploy_docker.sh
```

#### Step 2: Test Docker image locally

```bash
# Test the image locally before deploying
docker run \
  -e AWS_PROFILE=ai-data-enrichment \
  -e OPENAI_API_KEY=sk-your-key \
  -v ~/.aws:/root/.aws:ro \
  bedrock-classifier:latest \
  python src/main_aws.py sample_10_test.csv docker-test-1
```

---

### Option 3: Deploy to ECS (Production - 30 min)

After Docker image is in ECR, you can deploy to ECS for production:

**This requires:**
1. ✅ ECR image (from Option 2)
2. ❌ ECS cluster (needs to be created)
3. ❌ ECS task definition (needs to be created)
4. ❌ ECS service (needs to be created)

**I can create Terraform for this if you want to deploy to ECS.**

---

## My Recommendation

### For Testing/POC (Right Now):
**Use Option 1** - Run directly with Python + AWS integration

### For Small Production Runs:
**Use Option 2** - Docker on EC2 instance
- Launch EC2 (t3.large)
- Pull image from ECR
- Run processing

### For Large Scale Production:
**Use Option 3** - ECS Fargate with auto-scaling
- Needs additional Terraform infrastructure
- Auto-scales based on queue depth
- More complex but fully managed

---

## What Do You Want to Do?

1. **Test now** → Use Option 1 (no Docker needed)
2. **Create Docker image** → Run `./infrastructure/deploy_docker.sh`
3. **Deploy to production** → Need ECS infrastructure (I can create this)

Which path do you want to take?

