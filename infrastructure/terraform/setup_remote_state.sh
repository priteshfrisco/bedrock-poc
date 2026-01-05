#!/bin/bash
# Setup Remote State Backend for Terraform
# Creates S3 bucket and DynamoDB table for state management

set -e

echo "=============================================="
echo "Terraform Remote State Backend Setup"
echo "=============================================="
echo ""

# Configuration
REGION="${AWS_REGION:-us-east-2}"
STATE_BUCKET="${TERRAFORM_STATE_BUCKET:-bedrock-ai-terraform-state}"
LOCK_TABLE="${TERRAFORM_LOCK_TABLE:-bedrock-ai-terraform-locks}"

echo "Configuration:"
echo "  Region: $REGION"
echo "  State Bucket: $STATE_BUCKET"
echo "  Lock Table: $LOCK_TABLE"
echo ""

# Check AWS credentials
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "❌ AWS credentials not configured"
    echo "Run: aws configure"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "✅ AWS Account: $ACCOUNT_ID"
echo ""

# Create S3 bucket for state
echo "Step 1: Creating S3 bucket for Terraform state..."
if aws s3 ls "s3://$STATE_BUCKET" 2>&1 | grep -q 'NoSuchBucket'; then
    aws s3api create-bucket \
        --bucket "$STATE_BUCKET" \
        --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION"
    
    # Enable versioning
    aws s3api put-bucket-versioning \
        --bucket "$STATE_BUCKET" \
        --versioning-configuration Status=Enabled
    
    # Enable encryption
    aws s3api put-bucket-encryption \
        --bucket "$STATE_BUCKET" \
        --server-side-encryption-configuration '{
            "Rules": [{
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "AES256"
                }
            }]
        }'
    
    # Block public access
    aws s3api put-public-access-block \
        --bucket "$STATE_BUCKET" \
        --public-access-block-configuration \
            "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    
    echo "✅ Created S3 bucket: $STATE_BUCKET"
else
    echo "✅ S3 bucket already exists: $STATE_BUCKET"
fi
echo ""

# Create DynamoDB table for state locking
echo "Step 2: Creating DynamoDB table for state locking..."
if ! aws dynamodb describe-table --table-name "$LOCK_TABLE" --region "$REGION" > /dev/null 2>&1; then
    aws dynamodb create-table \
        --table-name "$LOCK_TABLE" \
        --attribute-definitions AttributeName=LockID,AttributeType=S \
        --key-schema AttributeName=LockID,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "$REGION" \
        --tags Key=Name,Value="Terraform State Lock" Key=Purpose,Value="State Locking"
    
    echo "✅ Created DynamoDB table: $LOCK_TABLE"
    echo "⏳ Waiting for table to be active..."
    aws dynamodb wait table-exists --table-name "$LOCK_TABLE" --region "$REGION"
else
    echo "✅ DynamoDB table already exists: $LOCK_TABLE"
fi
echo ""

echo "=============================================="
echo "✅ Remote State Backend Setup Complete!"
echo "=============================================="
echo ""
echo "Next Steps:"
echo ""
echo "1. Update main.tf with your bucket name:"
echo "   Uncomment the backend block and update:"
echo "   - bucket: $STATE_BUCKET"
echo "   - dynamodb_table: $LOCK_TABLE"
echo ""
echo "2. Initialize Terraform with the backend:"
echo "   cd infrastructure/terraform"
echo "   terraform init -migrate-state"
echo ""
echo "3. Verify state is in S3:"
echo "   aws s3 ls s3://$STATE_BUCKET/infrastructure/"
echo ""
echo "Cost: ~\$0.50/month (S3 + DynamoDB)"
echo ""

