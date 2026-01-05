#!/bin/bash
# Upload Reference Data to S3

set -e

# Get bucket name from argument or terraform output
if [ -n "$1" ]; then
    REFERENCE_BUCKET="$1"
else
    echo "Getting reference bucket name from Terraform..."
    cd "$(dirname "$0")/terraform"
    REFERENCE_BUCKET=$(terraform output -raw reference_bucket_name 2>/dev/null)
    cd ..
fi

if [ -z "$REFERENCE_BUCKET" ]; then
    echo "❌ Error: Reference bucket name not provided"
    echo "Usage: $0 <bucket-name>"
    echo "Or run from deploy.sh which passes it automatically"
    exit 1
fi

REGION="${AWS_REGION:-us-east-2}"

echo "=========================================="
echo "Uploading Reference Data to S3"
echo "=========================================="
echo ""
echo "Bucket: s3://$REFERENCE_BUCKET/"
echo "Region: $REGION"
echo ""

# Check if reference_data directory exists
if [ ! -d "reference_data" ]; then
    echo "❌ Error: reference_data/ directory not found"
    echo "Run this script from the project root directory"
    exit 1
fi

# Upload all reference data files
echo "Uploading files..."
aws s3 sync reference_data/ s3://$REFERENCE_BUCKET/ \
  --exclude "backup/*" \
  --region $REGION

echo ""
echo "✅ Reference data uploaded!"
echo ""
echo "Files in bucket:"
aws s3 ls s3://$REFERENCE_BUCKET/ --region $REGION

echo ""
echo "=========================================="
