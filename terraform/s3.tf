# --- S3 Bucket for Medical Documents ---
module "documents_bucket" {
  source  = "terraform-aws-modules/s3-bucket/aws"
  version = "~> 4.0"

  bucket        = "medilink-docs-production-bucket"
  force_destroy = true

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

