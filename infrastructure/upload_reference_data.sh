#!/bin/bash
# Upload Reference Data to S3

set -e

# Get bucket name and prefix from arguments or terraform output
if [ -n "$1" ]; then
    S3_BUCKET="$1"
    REFERENCE_PREFIX="${2:-reference/}"
else
    echo "Getting S3 bucket name from Terraform..."
    cd "$(dirname "$0")/terraform"
    S3_BUCKET=$(terraform output -raw s3_bucket_name 2>/dev/null)
    REFERENCE_PREFIX="reference/"
    cd ..
fi

if [ -z "$S3_BUCKET" ]; then
    echo "❌ Error: S3 bucket name not provided"
    echo "Usage: $0 <bucket-name> [reference-prefix]"
    echo "Or run from deploy.sh which passes it automatically"
    exit 1
fi

REGION="${AWS_REGION:-us-east-2}"

echo "=========================================="
echo "Uploading Reference Data to S3"
echo "=========================================="
echo ""
echo "Bucket: s3://$S3_BUCKET/$REFERENCE_PREFIX"
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
aws s3 sync reference_data/ s3://$S3_BUCKET/$REFERENCE_PREFIX \
  --exclude "backup/*" \
  --region $REGION

echo ""
echo "✅ Reference data uploaded!"
echo ""
echo "Files in bucket:"
aws s3 ls s3://$S3_BUCKET/$REFERENCE_PREFIX --region $REGION

echo ""
echo "=========================================="
