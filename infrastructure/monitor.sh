#!/bin/bash
# Monitor current processing status
# Usage: ./monitor.sh

BUCKET="bedrock-ai-data-enrichment-data-t916aj65"
CLUSTER="bedrock-ai-data-enrichment-cluster"
REGION="us-east-2"
PROFILE=${AWS_PROFILE:-ai-data-enrichment}

echo "=========================================="
echo "Processing Status Monitor"
echo "=========================================="
echo ""

# Check ECS tasks
echo "ECS Tasks:"
TASKS=$(aws ecs list-tasks --cluster $CLUSTER --region $REGION --profile $PROFILE --output text)
if [ -z "$TASKS" ]; then
    echo "  No tasks running"
else
    echo "  Task is running"
    TASK_ID=$(echo $TASKS | awk '{print $2}' | cut -d'/' -f3)
    aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ID --region $REGION --profile $PROFILE \
      --query 'tasks[0].{Status:lastStatus,Started:startedAt}' --output table
fi

echo ""

# Check S3 output
echo "S3 Output Files:"
OUTPUT=$(aws s3 ls s3://$BUCKET/output/ --recursive --profile $PROFILE 2>/dev/null)
if [ -z "$OUTPUT" ]; then
    echo "  No output files yet..."
else
    echo "$OUTPUT" | tail -5
fi

echo ""
echo "=========================================="
