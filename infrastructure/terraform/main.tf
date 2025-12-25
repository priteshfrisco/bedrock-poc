# Terraform Configuration for Bedrock AI Data Enrichment
# Run: terraform init && terraform apply

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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

# Get current AWS account ID
data "aws_caller_identity" "current" {}

# Local variables
locals {
  account_id    = data.aws_caller_identity.current.account_id
  name_prefix   = "${var.client_name}-${var.project_name}"
  
  # S3 bucket names (globally unique)
  input_bucket  = "${local.name_prefix}-input-${local.account_id}"
  output_bucket = "${local.name_prefix}-output-${local.account_id}"
  audit_bucket  = "${local.name_prefix}-audit-${local.account_id}"
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

# Audit bucket for prompts/responses
resource "aws_s3_bucket" "audit" {
  bucket = local.audit_bucket
  
  tags = {
    Name    = "Audit-Logs-Bucket"
    Purpose = "Stores-prompts-responses-and-audit-trail"
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
# DYNAMODB TABLE
# ============================================================================

# State tracking table
resource "aws_dynamodb_table" "processing_state" {
  name           = "${local.name_prefix}-processing-state"
  billing_mode   = "PAY_PER_REQUEST"  # Serverless, no capacity planning
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
  
  # Global secondary index for querying by status
  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "status"
    range_key       = "asin"
    projection_type = "ALL"
  }
  
  # Enable point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }
  
  tags = {
    Name = "Processing State Table"
    Purpose = "Tracks classification status per product"
  }
}

# ============================================================================
# IAM ROLE FOR APPLICATION
# ============================================================================

# IAM role for the application (ECS/Lambda/EC2)
resource "aws_iam_role" "app_role" {
  name = "${local.name_prefix}-app-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = [
            "ecs-tasks.amazonaws.com",
            "lambda.amazonaws.com",
            "ec2.amazonaws.com"
          ]
        }
      }
    ]
  })
  
  tags = {
    Name = "Application IAM Role"
  }
}

# Policy for S3 access
resource "aws_iam_role_policy" "s3_access" {
  name = "s3-access"
  role = aws_iam_role.app_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
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
          "${aws_s3_bucket.audit.arn}/*"
        ]
      }
    ]
  })
}

# Policy for DynamoDB access
resource "aws_iam_role_policy" "dynamodb_access" {
  name = "dynamodb-access"
  role = aws_iam_role.app_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
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
      }
    ]
  })
}

# Policy for CloudWatch Logs
resource "aws_iam_role_policy" "cloudwatch_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.app_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/${var.project_name}/*"
      }
    ]
  })
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

output "dynamodb_table_name" {
  description = "DynamoDB table for processing state"
  value       = aws_dynamodb_table.processing_state.id
}

output "iam_role_arn" {
  description = "IAM role ARN for application"
  value       = aws_iam_role.app_role.arn
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "setup_complete" {
  description = "Setup confirmation message"
  value       = <<-EOT
    ✅ Infrastructure created successfully!
    
    Resources:
      - Input Bucket:  s3://${aws_s3_bucket.input.id}
      - Output Bucket: s3://${aws_s3_bucket.output.id}
      - Audit Bucket:  s3://${aws_s3_bucket.audit.id}
      - DynamoDB Table: ${aws_dynamodb_table.processing_state.id}
      - IAM Role: ${aws_iam_role.app_role.name}
    
    Next steps:
      1. Build application code
      2. Create reference data files
      3. Test locally
      4. Deploy with Lambda (later)
  EOT
}

