#!/bin/bash
# S3 Cleanup Script - Remove old test files and logs
# Usage: ./cleanup_s3.sh [bucket-name]

set -e

BUCKET=${1:-bedrock-ai-data-enrichment-data-t916aj65}
PROFILE=${AWS_PROFILE:-ai-data-enrichment}

echo "=========================================="
echo "S3 Cleanup Script"
echo "=========================================="
echo "Bucket: $BUCKET"
echo "Profile: $PROFILE"
echo ""

# List what will be deleted
echo "📋 Current contents:"
aws s3 ls s3://$BUCKET/ --recursive --human-readable --profile $PROFILE | head -20

echo ""
read -p "⚠️  Delete ALL files in this bucket? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "❌ Cleanup cancelled"
    exit 0
fi

echo ""
echo "🗑️  Deleting all objects..."

# Delete all objects
aws s3 rm s3://$BUCKET/ --recursive --profile $PROFILE

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "Bucket is now empty and ready for fresh test."

