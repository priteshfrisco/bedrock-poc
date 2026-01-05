# Terraform Configuration

## Overview

This directory contains Terraform configuration for the complete Bedrock AI Data Enrichment infrastructure.

## Files

- **`main.tf`** - Complete infrastructure definition
- **`terraform.tfvars.example`** - Template for variables
- **`.gitignore`** - Excludes sensitive files from git
- **`setup_remote_state.sh`** - Script to create remote state backend

## Quick Start

### 1. Configure Variables

```bash
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars
```

Update:
- `notification_email` - Your email for notifications
- `openai_api_key` - Your OpenAI API key

### 2. Initialize Terraform

```bash
terraform init
```

### 3. Review Plan

```bash
terraform plan
```

### 4. Deploy

```bash
terraform apply
```

---

## Remote State (Recommended for Production)

### Why Remote State?

- ✅ State stored in S3 (not local machine)
- ✅ State locking prevents conflicts
- ✅ Team collaboration ready
- ✅ Encrypted at rest
- ✅ Versioned for rollback

### Setup Remote State

**Step 1: Create Backend Resources**

```bash
./setup_remote_state.sh
```

This creates:
- S3 bucket: `bedrock-ai-terraform-state`
- DynamoDB table: `bedrock-ai-terraform-locks`

**Step 2: Enable Backend in main.tf**

Uncomment the `backend` block in `main.tf`:

```hcl
backend "s3" {
  bucket         = "bedrock-ai-terraform-state"
  key            = "infrastructure/terraform.tfstate"
  region         = "us-east-2"
  encrypt        = true
  dynamodb_table = "bedrock-ai-terraform-locks"
}
```

**Step 3: Migrate State**

```bash
terraform init -migrate-state
```

Type `yes` when prompted.

**Step 4: Verify**

```bash
aws s3 ls s3://bedrock-ai-terraform-state/infrastructure/
```

You should see `terraform.tfstate`.

---

## Resources Created

### Storage
- **4 S3 Buckets** (input, output, audit, reference)
  - Versioning enabled
  - Encryption (AES256)
  - Public access blocked
  
### Compute
- **ECS Cluster** (Fargate)
- **ECS Task Definition** (4 vCPU, 8GB RAM)
- **Lambda Function** (S3 trigger)
- **ECR Repository** (Docker images)

### Database
- **DynamoDB Table** (processing state)

### Security
- **Security Group** (ECS tasks)
- **Secrets Manager** (OpenAI API key)
- **IAM Roles** (ECS execution, task, Lambda)

### Monitoring
- **CloudWatch Log Groups** (ECS + Lambda)
- **SNS Topic** (email notifications)

### Cost Estimate
- **Development:** ~$20-30/month
- **Production (2 files/month):** ~$50-100/month

---

## Important Commands

### View Current State
```bash
terraform show
```

### List All Resources
```bash
terraform state list
```

### Get Outputs
```bash
terraform output
```

### Destroy Everything
```bash
terraform destroy
```

⚠️ **Warning:** This deletes ALL resources including S3 buckets!

---

## State Management

### Local State (Default)
- **File:** `terraform.tfstate` (ignored by git)
- **Location:** This directory
- **Backup:** `terraform.tfstate.backup`

### Remote State (Recommended)
- **Storage:** S3 bucket
- **Locking:** DynamoDB table
- **Migration:** `terraform init -migrate-state`

---

## Troubleshooting

### "Error: Backend configuration changed"
```bash
terraform init -reconfigure
```

### "Error: State lock"
Someone else is running Terraform. Wait or:
```bash
# Force unlock (use with caution!)
terraform force-unlock LOCK_ID
```

### "Error: Resource already exists"
Import existing resource:
```bash
terraform import aws_s3_bucket.input bucket-name
```

---

## Security Notes

### ✅ **Tracked in Git:**
- `main.tf`
- `terraform.tfvars.example`
- `.terraform.lock.hcl`
- `.gitignore`

### ❌ **NOT Tracked (Sensitive):**
- `terraform.tfvars` (has your API key)
- `terraform.tfstate` (has resource IDs)
- `.terraform/` (downloaded providers)

---

## Upgrade Guide

### Update Provider Versions

1. Edit `main.tf` required_providers
2. Run `terraform init -upgrade`
3. Test with `terraform plan`
4. Apply with `terraform apply`

### Migrate State to Remote

See "Remote State" section above.

---

## Support

For issues:
1. Check `terraform.log` (if enabled)
2. Review AWS CloudWatch logs
3. Verify AWS credentials: `aws sts get-caller-identity`

