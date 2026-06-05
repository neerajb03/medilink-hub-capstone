# --- Customer-Managed KMS Key ---
data "aws_caller_identity" "current" {}

resource "aws_kms_key" "medilink" {
  description             = "MediLink Hub encryption key for RDS, S3, and Secrets Manager"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  rotation_period_in_days = 365

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootAccountFullAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowBackendRoleUsage"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.backend.arn
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })

  tags = { Name = "medilink-kms-key" }
}

resource "aws_kms_alias" "medilink" {
  name          = "alias/medilink-production-key"
  target_key_id = aws_kms_key.medilink.key_id
}
