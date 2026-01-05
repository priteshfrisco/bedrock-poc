# Bedrock AI Data Enrichment - Deployment Package

## Complete Production Setup (Single Command Deploy)

This is a **production-ready** deployment package that can be transferred to any client environment.

---

## 📦 What's Included

### Infrastructure (Terraform)
- **Single `main.tf` file** - Complete infrastructure as code
- S3 buckets (input/output/audit/reference)
- DynamoDB state tracking
- ECS Fargate cluster
- Lambda trigger
- SNS notifications
- CloudWatch Logs
- All IAM roles/permissions

### Application Code
- Python pipeline with GPT-5-mini
- AWS integration (S3, DynamoDB, SNS)
- Docker containerization
- Reference data (ingredient lookups, business rules)

### Deployment Scripts
- `deploy.sh` - One command to deploy everything
- `upload_reference_data.sh` - Upload CSVs/JSONs to S3
- `deploy_docker.sh` - Build and push Docker image
- `test_aws_setup.sh` - Verify AWS connectivity

---

## 🚀 One-Command Deployment

```bash
# Set your configuration
export TF_VAR_notification_email="your-email@company.com"
export TF_VAR_openai_api_key="sk-your-openai-key"
export AWS_PROFILE=your-aws-profile

# Deploy everything (takes ~15 minutes)
cd infrastructure
./deploy.sh
```

**That's it!** The script will:
1. ✅ Deploy Terraform infrastructure
2. ✅ Upload reference data to S3
3. ✅ Build and push Docker image to ECR
4. ✅ Test the setup
5. ✅ Show you next steps

---

## 📋 Prerequisites

1. **AWS Account** with permissions to create:
   - S3 buckets
   - DynamoDB tables
   - ECS clusters
   - Lambda functions
   - SNS topics
   - IAM roles

2. **Tools Installed:**
   - AWS CLI (`aws --version`)
   - Terraform (`terraform --version`)
   - Docker (`docker --version`)
   - Python 3.13+ (`python --version`)

3. **Credentials:**
   - AWS credentials configured (`aws configure`)
   - OpenAI API key
   - Email for notifications

---

## 🏗️ Architecture

```
Upload CSV → S3 Input Bucket
    ↓
S3 Event → Lambda Trigger
    ↓
Lambda → Starts ECS Fargate Task
    ↓
ECS Task → Processes 60K products (2-3 hours)
    ↓
ECS Task → Writes results to S3 Output Bucket
    ↓
ECS Task → Sends SNS email notification
    ↓
ECS Task → Auto-terminates
```

---

## 📊 Cost Estimate

**Per 60K product run:**
- OpenAI API: ~$60
- AWS (ECS + S3 + DynamoDB): ~$2
- **Total: ~$62 per run**

For 2 files/month: **~$124/month**

---

## 📁 File Structure

```
bedrock-poc/
├── infrastructure/
│   ├── terraform/
│   │   └── main.tf              # Single Terraform file
│   ├── deploy.sh                # One-command deployment
│   ├── deploy_docker.sh         # Docker build/push
│   ├── upload_reference_data.sh # Upload CSVs/JSONs
│   └── test_aws_setup.sh        # Verify setup
├── src/
│   ├── main_aws.py              # Cloud entry point
│   ├── main.py                  # Local entry point
│   ├── aws/                     # AWS integrations
│   ├── core/                    # Core logic
│   ├── llm/                     # LLM prompts/tools
│   └── pipeline/                # Processing steps
├── reference_data/              # Lookups & rules
├── Dockerfile                   # Container definition
└── requirements.txt             # Python dependencies
```

---

## 🔧 Configuration

All configuration in Terraform variables:

```hcl
# infrastructure/terraform/main.tf
variable "notification_email" {
  default = "your-email@company.com"
}

variable "openai_api_key" {
  default = "sk-your-key"
  sensitive = true
}

variable "aws_region" {
  default = "us-east-2"
}
```

Override with environment variables or `terraform.tfvars`:
```bash
export TF_VAR_notification_email="your-email"
export TF_VAR_openai_api_key="sk-key"
```

---

## 🧪 Testing

After deployment:

```bash
# Upload test file
aws s3 cp data/input/sample_10_test.csv s3://[input-bucket]/

# Watch logs in real-time
aws logs tail /ecs/bedrock-ai-data-enrichment-task --follow

# Check email for completion notification

# Download results
aws s3 cp s3://[output-bucket]/runs/[run-id]/sample_10_test_coded.csv ./
```

---

## 📧 Email Notifications

You'll receive emails for:
- ✅ **Success**: Processing complete with summary
- ❌ **Failure**: Error details with CloudWatch link

Example email:
```
✅ Processing Complete!

File: uncoded_60k_products.csv
Total Products: 60,000
Processed: 58,234
Duration: 142.3 minutes

Output: s3://[bucket]/runs/[run-id]/uncoded_60k_products_coded.csv
```

---

## 🗑️ Cleanup

To remove all resources:

```bash
cd infrastructure/terraform
terraform destroy
```

---

## 📖 Detailed Documentation

- `docs/COMPLETE_DEPLOYMENT.md` - Step-by-step deployment guide
- `docs/AWS_DEPLOYMENT.md` - AWS architecture details
- `docs/AWS_CHECKLIST.md` - Prerequisites checklist
- `docs/DOCKER_SETUP.md` - Docker deployment options

---

## 🤝 Client Handoff

**This package is ready to transfer to client:**

1. ✅ Single Terraform file (no fragmentation)
2. ✅ One-command deployment script
3. ✅ All configuration via environment variables
4. ✅ Professional documentation
5. ✅ Testing scripts included
6. ✅ Cost estimates provided
7. ✅ Cleanup instructions

**Transfer:** Just ZIP this entire folder and send to client.

---

## 🆘 Support

For issues:
1. Check CloudWatch Logs: `/ecs/bedrock-ai-data-enrichment-task`
2. Check DynamoDB table for per-product status
3. Review `docs/` folder for troubleshooting guides

---

## 📝 License & Credits

- Built with OpenAI GPT-5-mini
- AWS infrastructure managed by Terraform
- Python 3.13+ application

