#!/bin/bash
# Deploy Docker Image to AWS ECR

set -e

REGION="us-east-2"
ACCOUNT_ID="081671069810"
REPO_NAME="bedrock-classifier"
IMAGE_TAG="latest"

echo "=========================================="
echo "Docker Image Deployment to ECR"
echo "=========================================="

# Step 1: Create ECR repository (if doesn't exist)
echo ""
echo "Step 1: Creating ECR repository..."
aws ecr describe-repositories --repository-names $REPO_NAME --region $REGION 2>/dev/null || \
aws ecr create-repository \
  --repository-name $REPO_NAME \
  --region $REGION \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256

echo "✅ ECR repository ready: $REPO_NAME"

# Step 2: Build Docker image
echo ""
echo "Step 2: Building Docker image..."
docker build -t $REPO_NAME:$IMAGE_TAG .
echo "✅ Docker image built"

# Step 3: Login to ECR
echo ""
echo "Step 3: Logging in to ECR..."
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
echo "✅ Logged in to ECR"

# Step 4: Tag image
echo ""
echo "Step 4: Tagging image..."
docker tag $REPO_NAME:$IMAGE_TAG $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME:$IMAGE_TAG
echo "✅ Image tagged"

# Step 5: Push to ECR
echo ""
echo "Step 5: Pushing image to ECR..."
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME:$IMAGE_TAG
echo "✅ Image pushed to ECR"

# Get image URI
IMAGE_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME:$IMAGE_TAG"

echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "Image URI: $IMAGE_URI"
echo ""
echo "Next steps:"
echo "1. Test locally: docker run -e OPENAI_API_KEY=sk-... $REPO_NAME:$IMAGE_TAG"
echo "2. Deploy to ECS/EC2 using the image URI above"
echo "3. Or run on EC2:"
echo "   docker run -e OPENAI_API_KEY=sk-... $IMAGE_URI python src/main_aws.py sample_10_test.csv run-001"

