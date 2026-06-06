# MediLink Hub — Production Architecture Upgrade

This repository contains a fully decoupled, highly available, and secure production architecture for the MediLink Hub microservices application, deployed on AWS via Terraform.

## 🚀 Key Architectural Upgrades

### 1. Zero Trust & Encryption at Rest
*   **AWS KMS**: All sensitive data stores are encrypted at rest using a Customer Managed Symmetric Key (`alias/medilink-production-key`) with 365-day auto-rotation.
*   **AWS Secrets Manager**: Hardcoded database passwords and JWT secrets have been entirely eliminated. Credentials are dynamically generated, stored in Secrets Manager, and retrieved at runtime by the FastAPI microservices using `boto3`.
*   **SSE-KMS S3 Encryption**: Medical document uploads are secured with AWS KMS server-side encryption.

### 2. Event-Driven Notification Pipeline
*   **Decoupled Workers**: Notification processing has been decoupled from the API layer using **Amazon SQS** and **AWS Lambda**.
*   **Dead Letter Queues (DLQ)**: An SQS DLQ captures any failed notification events after 3 retries, ensuring zero dropped messages and enabling replay capabilities.
*   **Amazon SNS**: The Lambda worker processes the SQS events and fans out notifications via SNS.

### 3. Network Security & Cost Optimization
*   **Interface VPC Endpoints (PrivateLink)**: Added VPC Endpoints for `secretsmanager`, `sqs`, `sns`, and `logs`. This ensures that all AWS API calls made by the private EC2 instances never traverse the public internet or the NAT Gateway, drastically reducing data processing costs and improving security.
*   **S3 Gateway Endpoint**: S3 traffic is routed purely through the AWS backbone via prefix lists injected into the private route tables.

### 4. Dynamic Auto Scaling
*   **Target Tracking Policies**: The backend Auto Scaling Group (ASG) utilizes an `ASGAverageCPUUtilization` policy targeted at 50%, ensuring the microservices scale out dynamically under load and scale in to save costs during idle periods.

### 5. AI Symptom Checker Integration
*   **Hugging Face Serverless Inference**: The `health-service` integrates an asynchronous AI symptom checker powered by `HuggingFaceH4/zephyr-7b-beta`, keeping the architecture lean while providing powerful AI capabilities.

### 6. Observability
*   **CloudWatch Logging**: All microservices use structured JSON logging.
*   **Proactive Alarming**: Critical operations alarms (ALB 5xx errors and SQS DLQ depth) are wired up to an Operations SNS topic to alert engineers of system degradation.

## 🛠️ Technology Stack
*   **Infrastructure as Code**: Terraform
*   **Backend**: Python, FastAPI, SQLAlchemy, asyncpg
*   **Database**: PostgreSQL (Amazon RDS)
*   **Cloud Provider**: AWS (VPC, EC2, ASG, ALB, KMS, Secrets Manager, SQS, SNS, Lambda, CloudWatch, S3)
