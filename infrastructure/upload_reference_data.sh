#!/bin/bash
# Upload Reference Data to S3

set -e

REFERENCE_BUCKET="bedrock-ai-data-enrichment-reference-081671069810"
REGION="us-east-2"

echo "=========================================="
echo "Uploading Reference Data to S3"
echo "=========================================="

echo ""
echo "Uploading to s3://$REFERENCE_BUCKET/"

# Upload all reference data files
aws s3 sync reference_data/ s3://$REFERENCE_BUCKET/ \
  --exclude "backup/*" \
  --region $REGION

echo ""
echo "✅ Reference data uploaded!"
echo ""
echo "Files uploaded:"
aws s3 ls s3://$REFERENCE_BUCKET/ --region $REGION

