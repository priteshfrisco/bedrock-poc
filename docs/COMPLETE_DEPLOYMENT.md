# Complete Production POC Deployment

## What This Includes

✅ **S3 Event Trigger** - Auto-starts when CSV uploaded  
✅ **ECS Fargate** - Processes 60K products (unlimited runtime)  
✅ **Auto-termination** - Task stops after completion  
✅ **Email Notifications** - Success/failure alerts  
✅ **CloudWatch Logs** - All logs in one place  
✅ **Reference Data in S3** - No hardcoded files  
✅ **DynamoDB Tracking** - Per-product status  

---

## Step-by-Step Deployment

### Step 1: Deploy Terraform Infrastructure

```bash
cd /Users/priteshfrisco/Desktop/bedrock-poc/infrastructure/terraform

# Set your email and OpenAI key
export TF_VAR_notification_email="your-email@company.com"
export TF_VAR_openai_api_key="sk-your-key"

# Deploy complete infrastructure
terraform init
terraform plan -out=plan.out
terraform apply plan.out
```

**This creates:**
- 4 S3 buckets (input, output, audit, reference)
- DynamoDB table
- ECR repository
- ECS cluster + task definition
- Lambda trigger function
- SNS topic with email subscription
- CloudWatch log groups
- All IAM roles and permissions

**Time: ~5 minutes**

---

### Step 2: Confirm Email Subscription

After Terraform completes:
1. Check your email
2. Click "Confirm subscription" link from AWS
3. You'll receive notifications when jobs complete

---

### Step 3: Upload Reference Data to S3

```bash
cd /Users/priteshfrisco/Desktop/bedrock-poc
export AWS_PROFILE=ai-data-enrichment

./infrastructure/upload_reference_data.sh
```

**This uploads:**
- ingredient_category_lookup.csv
- amazon_subcategory_lookup.csv
- All extraction rules JSONs
- Business rules JSON

**Time: ~1 minute**

---

### Step 4: Build & Push Docker Image

```bash
export AWS_PROFILE=ai-data-enrichment
./infrastructure/deploy_docker.sh
```

**This:**
- Creates ECR repository
- Builds Docker image
- Pushes to ECR

**Time: ~10 minutes**

---

### Step 5: Test It!

```bash
# Upload a test file
aws s3 cp data/input/sample_10_test.csv s3://[input-bucket]/

# Watch what happens:
# 1. Lambda triggers (within seconds)
# 2. ECS task starts
# 3. Processing begins
# 4. Email arrives when complete
```

**Monitor in real-time:**
```bash
# Watch CloudWatch Logs
aws logs tail /ecs/bedrock-ai-data-enrichment-task --follow

# Check ECS tasks
aws ecs list-tasks --cluster bedrock-ai-data-enrichment-cluster

# Download results
aws s3 cp s3://[output-bucket]/runs/[run-id]/sample_10_test_coded.csv ./
```

---

## How It Works (60K Products)

**Upload File:**
```bash
aws s3 cp your_60k_file.csv s3://[input-bucket]/
```

**Automatic Flow:**
1. ⚡ S3 event triggers Lambda (instant)
2. 🚀 Lambda starts ECS Fargate task
3. 📥 ECS downloads CSV from S3
4. ⚙️  ECS processes 60K products (~2-3 hours)
5. 📤 ECS uploads results to S3
6. 📧 Email sent with summary
7. ✅ ECS task terminates automatically

**You get an email like:**
```
✅ Processing Complete!

File: uncoded_60k_products.csv
Run ID: run-20260105-140532
Total Products: 60,000
Processed: 58,234
Duration: 142.3 minutes

Output: s3://[bucket]/runs/run-20260105-140532/uncoded_60k_products_coded.csv
```

---

## Cost for 60K Products

**OpenAI API:**
- ~60K products × $0.001/product = ~$60

**AWS:**
- ECS Fargate (4 vCPU, 8GB, 3 hours): ~$0.50
- S3 storage + requests: ~$1
- DynamoDB: ~$0.50
- CloudWatch Logs: ~$0.25

**Total: ~$62 per run**

For 2 files/month: ~$124/month

---

## Monitoring & Debugging

**CloudWatch Logs:**
```bash
aws logs tail /ecs/bedrock-ai-data-enrichment-task --follow
```

**Check DynamoDB:**
```bash
aws dynamodb scan \
  --table-name bedrock-ai-data-enrichment-processing-state \
  --filter-expression "run_id = :run" \
  --expression-attribute-values '{":run":{"S":"run-20260105-140532"}}'
```

**List All Runs:**
```bash
aws s3 ls s3://[output-bucket]/runs/
```

---

## Cleanup (If Needed)

```bash
cd infrastructure/terraform
terraform destroy
```

---

## Next Steps After Deployment

1. ✅ Deploy infrastructure (`terraform apply`)
2. ✅ Confirm email subscription
3. ✅ Upload reference data
4. ✅ Build & push Docker
5. ✅ Test with sample file
6. ✅ Upload 60K file when ready

**Everything is automated after step 6!**

