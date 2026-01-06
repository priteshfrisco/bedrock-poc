#!/bin/bash
# Clear DynamoDB table data
# Usage: ./cleanup_dynamodb.sh

set -e

TABLE="bedrock-ai-data-enrichment-processing-state"
PROFILE=${AWS_PROFILE:-ai-data-enrichment}
REGION="us-east-2"

echo "=========================================="
echo "DynamoDB Cleanup Script"
echo "=========================================="
echo "Table: $TABLE"
echo "Profile: $PROFILE"
echo "Region: $REGION"
echo ""

# Count items first
ITEM_COUNT=$(aws dynamodb scan --table-name $TABLE \
  --select COUNT --region $REGION --profile $PROFILE \
  --output json | grep -o '"Count": [0-9]*' | grep -o '[0-9]*')

echo "📊 Current items: $ITEM_COUNT"

if [ "$ITEM_COUNT" -eq 0 ]; then
    echo "✅ Table is already empty!"
    exit 0
fi

echo ""
read -p "⚠️  Delete all $ITEM_COUNT items? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "❌ Cleanup cancelled"
    exit 0
fi

echo ""
echo "🗑️  Deleting all items..."

# Scan and delete all items
aws dynamodb scan --table-name $TABLE --region $REGION --profile $PROFILE \
  --attributes-to-get "asin" "run_id" --output json | \
  jq -r '.Items[] | @json' | \
  while read item; do
    asin=$(echo $item | jq -r '.asin.S')
    run_id=$(echo $item | jq -r '.run_id.S')
    
    aws dynamodb delete-item --table-name $TABLE --region $REGION --profile $PROFILE \
      --key "{\"asin\":{\"S\":\"$asin\"},\"run_id\":{\"S\":\"$run_id\"}}" \
      > /dev/null
    
    echo "  ✓ Deleted: $asin / $run_id"
  done

echo ""
echo "✅ DynamoDB cleanup complete!"

