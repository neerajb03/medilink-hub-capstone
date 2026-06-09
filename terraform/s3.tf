# --- S3 Bucket for Medical Documents ---
module "documents_bucket" {
  source  = "terraform-aws-modules/s3-bucket/aws"
  version = "~> 4.0"

  bucket        = "medilink-docs-production-bucket"
  force_destroy = false

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true

  server_side_encryption_configuration = {
    rule = {
      apply_server_side_encryption_by_default = {
        kms_master_key_id = aws_kms_key.medilink.arn
        sse_algorithm     = "aws:kms"
      }
      bucket_key_enabled = true
    }
  }

  cors_rule = [
    {
      allowed_headers = ["*"]
      allowed_methods = ["PUT", "POST", "GET"]
      allowed_origins = ["*"]
      expose_headers  = ["ETag"]
      max_age_seconds = 3000
    }
  ]
}

# --- Zero-Downtime State Migration (Moved Blocks) ---
moved {
  from = aws_s3_bucket.documents
  to   = module.documents_bucket.aws_s3_bucket.this[0]
}

moved {
  from = aws_s3_bucket_cors_configuration.documents_cors
  to   = module.documents_bucket.aws_s3_bucket_cors_configuration.this[0]
}

moved {
  from = aws_s3_bucket_server_side_encryption_configuration.documents_enc
  to   = module.documents_bucket.aws_s3_bucket_server_side_encryption_configuration.this[0]
}

moved {
  from = aws_s3_bucket_public_access_block.documents_block
  to   = module.documents_bucket.aws_s3_bucket_public_access_block.this[0]
}

# --- IAM Policy for Private EC2 Instances to Access S3 Bucket ---
resource "aws_iam_role" "backend" {
  name = "medilink-backend-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "backend_consolidated" {
  name = "medilink-backend-consolidated-policy"
  role = aws_iam_role.backend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 Access
      {
        Sid    = "S3Access"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"
        ]
        Resource = "${module.documents_bucket.s3_bucket_arn}/*"
      },
      {
        Sid    = "S3List"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = module.documents_bucket.s3_bucket_arn
      },
      # Secrets Manager
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.db_credentials.arn,
          aws_secretsmanager_secret.jwt_secret.arn,
          aws_secretsmanager_secret.hf_api_key.arn,
          aws_secretsmanager_secret.groq_api_key.arn
        ]
      },
      # KMS Encrypt + Decrypt
      {
        Sid    = "KMSUsage"
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:DescribeKey",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.medilink.arn
      },
      # SQS (Send only)
      {
        Sid    = "SQSSend"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.appointment_events.arn
      },
      # CloudWatch Logs
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
          "logs:DescribeLogGroups"
        ]
        Resource = "arn:aws:logs:us-east-1:*:log-group:/medilink/*"
      },
      # CloudWatch Metrics
      {
        Sid    = "CloudWatchMetrics"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "MediLink/Backend"
          }
        }
      },
      # SSM for CloudWatch Agent
      {
        Sid    = "SSMForCloudWatchAgent"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter"
        ]
        Resource = "arn:aws:ssm:us-east-1:*:parameter/AmazonCloudWatch-*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "backend" {
  name = "medilink-backend-instance-profile"
  role = aws_iam_role.backend.name
}

# Attach AWS managed policy for Systems Manager (SSM) Session Manager access
resource "aws_iam_role_policy_attachment" "backend_ssm" {
  role       = aws_iam_role.backend.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
