# Bedrock AI Data Enrichment System

## Introduction

This application is deployed on AWS cloud infrastructure and processes supplement product data using AI. 

The system runs as a Docker container on **AWS ECS Fargate** with dedicated compute resources (4 vCPU, 8GB RAM). When you upload a CSV file to S3, a Lambda function detects it and automatically launches an ECS Fargate task to process the data. Once processing completes, the task shuts down.

All data is stored in a single S3 bucket organized into folders:
- **input/**: Where you upload CSV files to be processed
- **output/**: Where the enriched/coded data is saved
- **audit/**: Stores detailed JSON logs of every AI decision made
- **logs/**: Contains processing logs and system information
- **reference/**: Stores lookup tables (ingredient database, business rules, etc.)

The AI processing uses **OpenAI's GPT models** (via API). When a product needs to be analyzed, the system sends the product information to OpenAI, which returns structured data about ingredients, categories, forms, and other details. The OpenAI API key is securely stored in AWS Secrets Manager.

**DynamoDB** is used to track the processing state of each product, ensuring no duplicates and allowing you to resume if processing is interrupted.

**SNS (Simple Notification Service)** sends email notifications when processing starts and completes, so you know exactly when your data is ready.

You can monitor real-time progress and logs through **CloudWatch**, which captures all system output and processing details.

The Docker image is stored in **AWS ECR (Elastic Container Registry)**, making it easy to update the application code by simply pushing a new image.

---


