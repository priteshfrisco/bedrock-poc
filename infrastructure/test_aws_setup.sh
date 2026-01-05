#!/bin/bash
# Quick AWS Setup and Test Script

set -e

echo "=========================================="
echo "Bedrock POC - AWS Setup & Test"
echo "=========================================="

# Configuration
INPUT_BUCKET="bedrock-ai-data-enrichment-input-081671069810"
OUTPUT_BUCKET="bedrock-ai-data-enrichment-output-081671069810"
AUDIT_BUCKET="bedrock-ai-data-enrichment-audit-081671069810"
DYNAMODB_TABLE="bedrock-ai-data-enrichment-processing-state"
REGION="us-east-2"

echo ""
echo "Step 1: Verifying AWS credentials..."
aws sts get-caller-identity --region $REGION || {
    echo "❌ AWS credentials not configured"
    echo "Run: aws configure"
    exit 1
}
echo "✅ AWS credentials OK"

echo ""
echo "Step 2: Checking if input bucket exists..."
aws s3 ls s3://$INPUT_BUCKET --region $REGION || {
    echo "❌ Cannot access input bucket"
    echo "Check permissions for: $INPUT_BUCKET"
    exit 1
}
echo "✅ Input bucket accessible"

echo ""
echo "Step 3: Uploading sample data to S3..."
if [ -f "data/input/sample_10_test.csv" ]; then
    aws s3 cp data/input/sample_10_test.csv s3://$INPUT_BUCKET/ --region $REGION
    echo "✅ Uploaded sample_10_test.csv"
else
    echo "⚠️  sample_10_test.csv not found, skipping upload"
fi

echo ""
echo "Step 4: Listing files in input bucket..."
aws s3 ls s3://$INPUT_BUCKET/ --region $REGION

echo ""
echo "Step 5: Checking DynamoDB table..."
aws dynamodb describe-table --table-name $DYNAMODB_TABLE --region $REGION > /dev/null 2>&1 || {
    echo "❌ Cannot access DynamoDB table"
    echo "Check permissions for: $DYNAMODB_TABLE"
    exit 1
}
echo "✅ DynamoDB table accessible"

echo ""
echo "=========================================="
echo "✅ AWS Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Set OPENAI_API_KEY environment variable"
echo "2. Run: PYTHONPATH=. python src/main_aws.py sample_10_test.csv test-run-1"
echo ""
echo "Or test locally with AWS integration:"
echo "  export AWS_PROFILE=your-profile"
echo "  export OPENAI_API_KEY=your-key"
echo "  PYTHONPATH=. python src/main_aws.py sample_10_test.csv test-run-1"

