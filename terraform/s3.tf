# --- S3 Bucket for Medical Documents ---
resource "aws_s3_bucket" "documents" {
  bucket        = "medilink-docs-production-bucket"
  force_destroy = false
}

# Enable Server Side Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "documents_enc" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block all Public Access to keep clinical records strictly private
resource "aws_s3_bucket_public_access_block" "documents_block" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- IAM Policy for Private EC2 Instances to Access S3 Bucket ---
resource "aws_iam_role" "backend_s3" {
  name = "medilink-backend-s3-role"

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

resource "aws_iam_policy" "s3_access" {
  name        = "medilink-s3-access-policy"
  description = "Permits document service instances to upload and read medical files"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.documents.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.documents.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "backend_s3" {
  role       = aws_iam_role.backend_s3.name
  policy_arn = aws_iam_policy.s3_access.arn
}

resource "aws_iam_instance_profile" "backend" {
  name = "medilink-backend-instance-profile"
  role = aws_iam_role.backend_s3.name
}
