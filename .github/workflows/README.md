# GitHub Actions CI/CD Pipeline

## Setup Instructions

### 1. Configure GitHub Secrets

Go to: `Repository Settings` → `Secrets and variables` → `Actions` → `New repository secret`

**Required Secrets:**
```
AWS_ACCESS_KEY_ID          # AWS access key for deployment account
AWS_SECRET_ACCESS_KEY      # AWS secret key for deployment account
NOTIFICATION_EMAIL         # Email for job notifications
OPENAI_API_KEY            # OpenAI API key (starts with sk-)
```

**Optional Secrets (have defaults):**
```
AWS_REGION                # Default: us-east-2
CLIENT_NAME               # Default: bedrock
PROJECT_NAME              # Default: ai-data-enrichment
```

### 2. Deploy

**Automatic (on push to main):**
```bash
git push origin main
```

**Manual (via GitHub UI):**
1. Go to `Actions` tab
2. Select `Deploy to AWS` workflow
3. Click `Run workflow`
4. Select environment (dev/staging/prod)
5. Click `Run workflow`

### 3. Monitor

- View deployment progress in `Actions` tab
- Check CloudWatch logs in AWS console
- Receive email notifications when jobs complete

## Workflow Stages

1. ✅ **Checkout** - Clone repository
2. ✅ **AWS Setup** - Configure credentials
3. ✅ **Terraform** - Setup remote state, init, plan, apply
4. ✅ **Reference Data** - Upload to S3
5. ✅ **Docker** - Build and push to ECR
6. ✅ **Summary** - Display deployment info

## Environment Variables

Set in workflow file or override via secrets:
- `AWS_REGION` - AWS region (default: us-east-2)
- `TF_VERSION` - Terraform version (default: 1.6.0)

## For Clients

Provide these 5 values:
1. AWS Access Key ID
2. AWS Secret Access Key
3. Email address
4. OpenAI API Key
5. AWS Region (optional)

Add as GitHub secrets, then push to deploy!

