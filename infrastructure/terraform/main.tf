# Terraform for Complete Production POC
# Lambda trigger → ECS Fargate → SNS notifications

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Client      = var.client_name
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Variables
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-2"
}

variable "client_name" {
  description = "Client name for tagging"
  type        = string
  default     = "bedrock"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "ai-data-enrichment"
}

variable "environment" {
  description = "Environment (dev, prod)"
  type        = string
  default     = "dev"
}

variable "notification_email" {
  description = "Email for job notifications"
  type        = string
  default     = "pshah@lakefusion.ai"  # UPDATE THIS
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

# Get current AWS account ID
data "aws_caller_identity" "current" {}

# Generate unique bucket suffix for global uniqueness
resource "random_string" "bucket_suffix" {
  length  = 8
  special = false
  upper   = false
}

# Local variables
locals {
  account_id    = data.aws_caller_identity.current.account_id
  name_prefix   = "${var.client_name}-${var.project_name}"
  bucket_suffix = random_string.bucket_suffix.result
  
  # S3 bucket names (globally unique with random suffix)
  input_bucket     = "${local.name_prefix}-input-${local.bucket_suffix}"
  output_bucket    = "${local.name_prefix}-output-${local.bucket_suffix}"
  audit_bucket     = "${local.name_prefix}-audit-${local.bucket_suffix}"
  reference_bucket = "${local.name_prefix}-reference-${local.bucket_suffix}"
}

# ============================================================================
# S3 BUCKETS
# ============================================================================

# Input bucket for uncoded CSVs
resource "aws_s3_bucket" "input" {
  bucket = local.input_bucket
  
  tags = {
    Name = "Input Data Bucket"
    Purpose = "Stores uncoded product CSV files"
  }
}

resource "aws_s3_bucket_versioning" "input" {
  bucket = aws_s3_bucket.input.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "input" {
  bucket = aws_s3_bucket.input.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "input" {
  bucket = aws_s3_bucket.input.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3 notification for Lambda trigger
resource "aws_s3_bucket_notification" "input_notification" {
  bucket = aws_s3_bucket.input.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.trigger.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".csv"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}

# Output bucket for coded CSVs
resource "aws_s3_bucket" "output" {
  bucket = local.output_bucket
  
  tags = {
    Name = "Output Data Bucket"
    Purpose = "Stores coded product CSV files and summaries"
  }
}

resource "aws_s3_bucket_versioning" "output" {
  bucket = aws_s3_bucket.output.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "output" {
  bucket = aws_s3_bucket.output.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "output" {
  bucket = aws_s3_bucket.output.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Audit bucket for prompts/responses
resource "aws_s3_bucket" "audit" {
  bucket = local.audit_bucket
  
  tags = {
    Name    = "Audit-Logs-Bucket"
    Purpose = "Stores-prompts-responses-and-audit-trail"
  }
}

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket = aws_s3_bucket.audit.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Reference data bucket
resource "aws_s3_bucket" "reference" {
  bucket = local.reference_bucket
  
  tags = {
    Name    = "Reference-Data-Bucket"
    Purpose = "Stores-ingredient-lookups-and-business-rules"
  }
}

resource "aws_s3_bucket_public_access_block" "reference" {
  bucket = aws_s3_bucket.reference.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reference" {
  bucket = aws_s3_bucket.reference.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Lifecycle policy for audit logs (delete after 90 days)
resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  
  rule {
    id     = "delete-old-audit-logs"
    status = "Enabled"
    
    filter {
      prefix = ""
    }
    
    expiration {
      days = 90
    }
  }
}

# ============================================================================
# SECRETS MANAGER (OpenAI API Key)
# ============================================================================

resource "aws_secretsmanager_secret" "openai_key" {
  name_prefix             = "${local.name_prefix}-openai-"
  recovery_window_in_days = 7
  
  tags = {
    Name = "OpenAI API Key"
  }
}

resource "aws_secretsmanager_secret_version" "openai_key" {
  secret_id     = aws_secretsmanager_secret.openai_key.id
  secret_string = var.openai_api_key
}

# ============================================================================
# DYNAMODB TABLE
# ============================================================================

resource "aws_dynamodb_table" "processing_state" {
  name           = "${local.name_prefix}-processing-state"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "asin"
  range_key      = "run_id"
  
  attribute {
    name = "asin"
    type = "S"
  }
  
  attribute {
    name = "run_id"
    type = "S"
  }
  
  attribute {
    name = "status"
    type = "S"
  }
  
  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "status"
    range_key       = "asin"
    projection_type = "ALL"
  }
  
  point_in_time_recovery {
    enabled = true
  }
  
  tags = {
    Name = "Processing State Table"
    Purpose = "Tracks classification status per product"
  }
}

# ============================================================================
# SNS TOPIC FOR NOTIFICATIONS
# ============================================================================

resource "aws_sns_topic" "notifications" {
  name = "${local.name_prefix}-notifications"
  
  tags = {
    Name = "Job Notifications Topic"
  }
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.notifications.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# ============================================================================
# CLOUDWATCH LOG GROUPS
# ============================================================================

resource "aws_cloudwatch_log_group" "ecs_tasks" {
  name              = "/ecs/${local.name_prefix}-task"
  retention_in_days = 30
  
  tags = {
    Name = "ECS Task Logs"
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name_prefix}-trigger"
  retention_in_days = 14
  
  tags = {
    Name = "Lambda Trigger Logs"
  }
}

# ============================================================================
# ECR REPOSITORY
# ============================================================================

resource "aws_ecr_repository" "app" {
  name                 = "bedrock-classifier"
  image_tag_mutability = "MUTABLE"
  
  image_scanning_configuration {
    scan_on_push = true
  }
  
  encryption_configuration {
    encryption_type = "AES256"
  }
  
  tags = {
    Name = "Application Container Repository"
  }
}

# ============================================================================
# SECURITY GROUP FOR ECS TASKS
# ============================================================================

# Get default VPC for security group
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "ecs_tasks" {
  name_prefix = "${local.name_prefix}-ecs-"
  description = "Security group for ECS tasks"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "Allow HTTPS outbound for API calls"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  egress {
    description = "Allow HTTP outbound"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "ECS Tasks Security Group"
  }
}

# ============================================================================
# ECS CLUSTER
# ============================================================================

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"
  
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  
  tags = {
    Name = "Processing Cluster"
  }
}

# ============================================================================
# IAM ROLES
# ============================================================================

# ECS Task Execution Role (for pulling images, writing logs)
resource "aws_iam_role" "ecs_execution_role" {
  name = "${local.name_prefix}-ecs-execution-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_role_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Secrets Manager access for ECS execution role
resource "aws_iam_role_policy" "ecs_secrets_access" {
  name = "secrets-access"
  role = aws_iam_role.ecs_execution_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = aws_secretsmanager_secret.openai_key.arn
    }]
  })
}

# ECS Task Role (for application permissions - S3, DynamoDB, SNS)
resource "aws_iam_role" "ecs_task_role" {
  name = "${local.name_prefix}-ecs-task-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

# S3 access policy
resource "aws_iam_role_policy" "ecs_s3_access" {
  name = "s3-access"
  role = aws_iam_role.ecs_task_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ]
      Resource = [
        aws_s3_bucket.input.arn,
        "${aws_s3_bucket.input.arn}/*",
        aws_s3_bucket.output.arn,
        "${aws_s3_bucket.output.arn}/*",
        aws_s3_bucket.audit.arn,
        "${aws_s3_bucket.audit.arn}/*",
        aws_s3_bucket.reference.arn,
        "${aws_s3_bucket.reference.arn}/*"
      ]
    }]
  })
}

# DynamoDB access policy
resource "aws_iam_role_policy" "ecs_dynamodb_access" {
  name = "dynamodb-access"
  role = aws_iam_role.ecs_task_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ]
      Resource = [
        aws_dynamodb_table.processing_state.arn,
        "${aws_dynamodb_table.processing_state.arn}/index/*"
      ]
    }]
  })
}

# SNS publish policy
resource "aws_iam_role_policy" "ecs_sns_publish" {
  name = "sns-publish"
  role = aws_iam_role.ecs_task_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sns:Publish"
      ]
      Resource = aws_sns_topic.notifications.arn
    }]
  })
}

# CloudWatch Logs policy
resource "aws_iam_role_policy" "ecs_cloudwatch_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.ecs_task_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      Resource = "${aws_cloudwatch_log_group.ecs_tasks.arn}:*"
    }]
  })
}

# Lambda execution role
resource "aws_iam_role" "lambda_role" {
  name = "${local.name_prefix}-lambda-trigger-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda ECS permissions
resource "aws_iam_role_policy" "lambda_ecs_access" {
  name = "ecs-access"
  role = aws_iam_role.lambda_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["ecs:RunTask"]
      Resource = aws_ecs_task_definition.app.arn
      Condition = {
        ArnEquals = {
          "ecs:cluster" = aws_ecs_cluster.main.arn
        }
      }
    }, {
      Effect = "Allow"
      Action = "iam:PassRole"
      Resource = [
        aws_iam_role.ecs_execution_role.arn,
        aws_iam_role.ecs_task_role.arn
      ]
    }]
  })
}

# ============================================================================
# ECS TASK DEFINITION
# ============================================================================

resource "aws_ecs_task_definition" "app" {
  family                   = "${local.name_prefix}-task"
  requires_compatibilities = ["FARGATE"]
  network_mode            = "awsvpc"
  cpu                     = "4096"  # 4 vCPU for 60K products
  memory                  = "8192"  # 8 GB RAM
  execution_role_arn      = aws_iam_role.ecs_execution_role.arn
  task_role_arn           = aws_iam_role.ecs_task_role.arn
  
  container_definitions = jsonencode([{
    name  = "bedrock-classifier"
    image = "${aws_ecr_repository.app.repository_url}:latest"
    
    essential = true
    
    environment = [
      {
        name  = "INPUT_BUCKET"
        value = aws_s3_bucket.input.id
      },
      {
        name  = "OUTPUT_BUCKET"
        value = aws_s3_bucket.output.id
      },
      {
        name  = "AUDIT_BUCKET"
        value = aws_s3_bucket.audit.id
      },
      {
        name  = "REFERENCE_BUCKET"
        value = aws_s3_bucket.reference.id
      },
      {
        name  = "DYNAMODB_TABLE"
        value = aws_dynamodb_table.processing_state.id
      },
      {
        name  = "SNS_TOPIC_ARN"
        value = aws_sns_topic.notifications.arn
      },
      {
        name  = "AWS_REGION"
        value = var.aws_region
      }
    ]
    
    secrets = [{
      name      = "OPENAI_API_KEY"
      valueFrom = aws_secretsmanager_secret.openai_key.arn
    }]
    
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ecs_tasks.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
  
  tags = {
    Name = "Processing Task Definition"
  }
}

# ============================================================================
# LAMBDA FUNCTION (Trigger)
# ============================================================================

# Lambda function code (inline for simplicity)
data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/lambda_trigger.zip"
  
  source {
    content  = <<-EOT
import json
import boto3
import os

ecs = boto3.client('ecs')

def lambda_handler(event, context):
    # Get S3 event details
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    print(f"File uploaded: s3://{bucket}/{key}")
    
    # Generate run ID
    import datetime
    run_id = f"run-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    # Start ECS task
    response = ecs.run_task(
        cluster=os.environ['ECS_CLUSTER'],
        taskDefinition=os.environ['TASK_DEFINITION'],
        launchType='FARGATE',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': os.environ['SUBNETS'].split(','),
                'securityGroups': [os.environ['SECURITY_GROUP']],
                'assignPublicIp': 'ENABLED'
            }
        },
        overrides={
            'containerOverrides': [{
                'name': 'bedrock-classifier',
                'command': ['python', 'src/main.py', '--mode', 'aws', '--input-key', key, '--run-id', run_id]
            }]
        }
    )
    
    task_arn = response['tasks'][0]['taskArn']
    print(f"Started ECS task: {task_arn}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Processing started',
            'task_arn': task_arn,
            'run_id': run_id
        })
    }
EOT
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "trigger" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${local.name_prefix}-trigger"
  role            = aws_iam_role.lambda_role.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  runtime         = "python3.13"
  timeout         = 60
  reserved_concurrent_executions = 3  # Limit concurrent executions for cost control
  
  environment {
    variables = {
      ECS_CLUSTER     = aws_ecs_cluster.main.name
      TASK_DEFINITION = aws_ecs_task_definition.app.family
      SUBNETS         = join(",", data.aws_subnets.default.ids)
      SECURITY_GROUP  = aws_security_group.ecs_tasks.id
    }
  }
  
  tags = {
    Name = "S3 Upload Trigger"
  }
}

# Allow S3 to invoke Lambda
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.trigger.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.input.arn
}

# ============================================================================
# OUTPUTS
# ============================================================================

output "input_bucket_name" {
  description = "S3 bucket for input CSV files"
  value       = aws_s3_bucket.input.id
}

output "output_bucket_name" {
  description = "S3 bucket for output CSV files"
  value       = aws_s3_bucket.output.id
}

output "audit_bucket_name" {
  description = "S3 bucket for audit logs"
  value       = aws_s3_bucket.audit.id
}

output "reference_bucket_name" {
  description = "S3 bucket for reference data"
  value       = aws_s3_bucket.reference.id
}

output "dynamodb_table_name" {
  description = "DynamoDB table for processing state"
  value       = aws_dynamodb_table.processing_state.id
}

output "sns_topic_arn" {
  description = "SNS topic for notifications"
  value       = aws_sns_topic.notifications.arn
}

output "ecr_repository_url" {
  description = "ECR repository URL for Docker images"
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "setup_complete" {
  description = "Setup instructions"
  value       = <<-EOT
    ✅ Complete Infrastructure Deployed!
    
    Resources:
      - Input Bucket:     s3://${aws_s3_bucket.input.id}
      - Output Bucket:    s3://${aws_s3_bucket.output.id}
      - Audit Bucket:     s3://${aws_s3_bucket.audit.id}
      - Reference Bucket: s3://${aws_s3_bucket.reference.id}
      - DynamoDB Table:   ${aws_dynamodb_table.processing_state.id}
      - SNS Topic:        ${aws_sns_topic.notifications.arn}
      - ECR Repository:   ${aws_ecr_repository.app.repository_url}
      - ECS Cluster:      ${aws_ecs_cluster.main.name}
    
    Next Steps:
      1. Upload reference data: ./infrastructure/upload_reference_data.sh
      2. Build & push Docker: ./infrastructure/deploy_docker.sh
      3. Test: Upload CSV to s3://${aws_s3_bucket.input.id}/
      4. Check email for completion notification
      5. Download results from s3://${aws_s3_bucket.output.id}/
  EOT
}

