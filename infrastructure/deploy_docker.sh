#!/bin/bash
# Deploy Docker Image to AWS ECR

set -e

# Get ECR repository URL from argument or terraform output
if [ -n "$1" ]; then
    ECR_REPO="$1"
else
    echo "Getting ECR repository URL from Terraform..."
    cd "$(dirname "$0")/terraform"
    ECR_REPO=$(terraform output -raw ecr_repository_url 2>/dev/null)
    cd ..
fi

if [ -z "$ECR_REPO" ]; then
    echo "❌ Error: ECR repository URL not provided"
    echo "Usage: $0 <ecr-repository-url>"
    echo "Or run from deploy.sh which passes it automatically"
    exit 1
fi

# Extract region and account from ECR URL
# Format: 123456789.dkr.ecr.us-east-2.amazonaws.com/repo-name
REGION=$(echo $ECR_REPO | cut -d'.' -f4)
ACCOUNT_ID=$(echo $ECR_REPO | cut -d'.' -f1)
REPO_NAME=$(echo $ECR_REPO | cut -d'/' -f2)
IMAGE_TAG="latest"

echo "=========================================="
echo "Docker Image Deployment to ECR"
echo "=========================================="
echo ""
echo "Repository: $ECR_REPO"
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Build from project root
cd "$(dirname "$0")/.."

# Step 1: Build Docker image
echo "Step 1: Building Docker image..."
docker build -t $REPO_NAME:$IMAGE_TAG -f Dockerfile .
echo "✅ Docker image built"

# Step 2: Login to ECR
echo ""
echo "Step 2: Logging in to ECR..."
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
echo "✅ Logged in to ECR"

# Step 3: Tag image
echo ""
echo "Step 3: Tagging image..."
docker tag $REPO_NAME:$IMAGE_TAG $ECR_REPO:$IMAGE_TAG
echo "✅ Image tagged"

# Step 4: Push to ECR
echo ""
echo "Step 4: Pushing image to ECR..."
docker push $ECR_REPO:$IMAGE_TAG
echo "✅ Image pushed to ECR"

echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "Image URI: $ECR_REPO:$IMAGE_TAG"
echo ""
echo "ECS will automatically use this image on next task launch."
echo ""
