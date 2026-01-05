#!/bin/bash
# One-Command Deployment for Bedrock AI Data Enrichment
# Professional production deployment script

set -e

echo "================================================================================"
echo "  BEDROCK AI DATA ENRICHMENT - PRODUCTION DEPLOYMENT"
echo "================================================================================"
echo ""

# Check prerequisites
echo "Step 1: Checking prerequisites..."
echo "-----------------------------------"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not installed. Install: https://aws.amazon.com/cli/"
    exit 1
fi
echo "✅ AWS CLI: $(aws --version | cut -d' ' -f1)"

# Check Terraform
if ! command -v terraform &> /dev/null; then
    echo "❌ Terraform not installed. Install: https://www.terraform.io/downloads"
    exit 1
fi
echo "✅ Terraform: $(terraform --version | head -1)"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not installed. Install: https://www.docker.com/get-started"
    exit 1
fi
echo "✅ Docker: $(docker --version)"

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS credentials not configured. Run: aws configure"
    exit 1
fi
echo "✅ AWS Account: $(aws sts get-caller-identity --query Account --output text)"

# Check required environment variables
if [ -z "$TF_VAR_notification_email" ]; then
    echo ""
    echo "⚠️  TF_VAR_notification_email not set"
    read -p "Enter notification email: " email
    export TF_VAR_notification_email="$email"
fi

if [ -z "$TF_VAR_openai_api_key" ]; then
    echo ""
    echo "⚠️  TF_VAR_openai_api_key not set"
    read -sp "Enter OpenAI API key: " apikey
    echo ""
    export TF_VAR_openai_api_key="$apikey"
fi

echo ""
echo "Configuration:"
echo "  Email: $TF_VAR_notification_email"
echo "  OpenAI Key: ${TF_VAR_openai_api_key:0:8}..."
echo ""

# Confirm deployment
read -p "Deploy infrastructure? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi

echo ""
echo "================================================================================"
echo "Step 2: Setting Up Remote State Backend"
echo "================================================================================"
echo ""

cd terraform

# Check if backend already exists
if aws s3 ls s3://bedrock-ai-terraform-state 2>/dev/null; then
    echo "✅ Remote state backend already exists"
else
    echo "Creating remote state backend (S3 + DynamoDB)..."
    ./setup_remote_state.sh
fi

echo ""
echo "================================================================================"
echo "Step 3: Deploying Terraform Infrastructure"
echo "================================================================================"
echo ""

# Initialize Terraform
echo "Initializing Terraform..."
terraform init

# Plan deployment
echo ""
echo "Planning deployment..."
terraform plan -out=deployment.tfplan

# Apply deployment
echo ""
echo "Applying deployment..."
terraform apply deployment.tfplan

# Get outputs
echo ""
echo "Getting resource names..."
INPUT_BUCKET=$(terraform output -raw input_bucket_name)
OUTPUT_BUCKET=$(terraform output -raw output_bucket_name)
REFERENCE_BUCKET=$(terraform output -raw reference_bucket_name)
ECR_REPO=$(terraform output -raw ecr_repository_url)
AWS_REGION=$(terraform output -raw aws_region)

cd ..

echo ""
echo "================================================================================"
echo "Step 4: Uploading Reference Data to S3"
echo "================================================================================"
echo ""

export AWS_REGION=$AWS_REGION
./upload_reference_data.sh "$REFERENCE_BUCKET"

echo ""
echo "================================================================================"
echo "Step 5: Building and Pushing Docker Image"
echo "================================================================================"
echo ""

./deploy_docker.sh "$ECR_REPO"

echo ""
echo "================================================================================"
echo "  ✅ DEPLOYMENT COMPLETE!"
echo "================================================================================"
echo ""
echo "Resources created:"
echo "  • Input Bucket:  s3://$INPUT_BUCKET"
echo "  • Output Bucket: s3://$OUTPUT_BUCKET"
echo "  • Reference Bucket: s3://$REFERENCE_BUCKET"
echo "  • ECR Repository: $ECR_REPO"
echo "  • Email notifications configured for: $TF_VAR_notification_email"
echo ""
echo "Next steps:"
echo "  1. Check your email and confirm SNS subscription"
echo "  2. Upload a CSV file to test:"
echo "     aws s3 cp your_file.csv s3://$INPUT_BUCKET/"
echo "  3. Processing will start automatically"
echo "  4. You'll receive an email when complete"
echo ""
echo "Monitor processing:"
echo "  • CloudWatch Logs: aws logs tail /ecs/bedrock-ai-data-enrichment-task --follow"
echo "  • ECS Tasks: aws ecs list-tasks --cluster bedrock-ai-data-enrichment-cluster"
echo ""
echo "View results:"
echo "  aws s3 ls s3://$OUTPUT_BUCKET/runs/"
echo ""
echo "To cleanup/destroy:"
echo "  cd terraform && terraform destroy"
echo ""
echo "================================================================================"

