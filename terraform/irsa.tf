# --- IRSA helper: builds the OIDC trust policy for a given K8s service account ---
locals {
  oidc_provider     = module.eks.oidc_provider
  oidc_provider_arn = module.eks.oidc_provider_arn
}

# Shared set of permissions needed by every backend service
data "aws_iam_policy_document" "common_sa_policy" {
  # Secrets Manager — pull DB creds, JWT keys, API keys
  statement {
    sid    = "SecretsManager"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [
      aws_secretsmanager_secret.db_credentials.arn,
      aws_secretsmanager_secret.jwt_rsa_private_key.arn,
      aws_secretsmanager_secret.jwt_rsa_public_key.arn,
    ]
  }
  # CloudWatch Logs — structured JSON logs from each pod
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = ["arn:aws:logs:us-east-1:${data.aws_caller_identity.current.account_id}:log-group:/medilink/*"]
  }
  # KMS — decrypt Secrets Manager and S3 objects
  statement {
    sid    = "KMSDecrypt"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.medilink.arn]
  }
}

# ─── user-service ─────────────────────────────────────────────────────────────
resource "aws_iam_role" "sa_user_service" {
  name = "medilink-sa-user-service"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider}:sub" = "system:serviceaccount:medilink:sa-user-service"
          "${local.oidc_provider}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "sa_user_service" {
  name   = "medilink-sa-user-service-policy"
  role   = aws_iam_role.sa_user_service.id
  policy = data.aws_iam_policy_document.common_sa_policy.json
}

# ─── appointment-service ──────────────────────────────────────────────────────
resource "aws_iam_role" "sa_appointment_service" {
  name = "medilink-sa-appointment-service"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider}:sub" = "system:serviceaccount:medilink:sa-appointment-service"
          "${local.oidc_provider}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "sa_appointment_service" {
  name   = "medilink-sa-appointment-service-policy"
  role   = aws_iam_role.sa_appointment_service.id
  policy = data.aws_iam_policy_document.common_sa_policy.json
}

resource "aws_iam_role_policy" "sa_appointment_sqs" {
  name = "medilink-sa-appointment-sqs"
  role = aws_iam_role.sa_appointment_service.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "SQSSend"
      Effect = "Allow"
      Action = ["sqs:SendMessage", "sqs:GetQueueUrl"]
      Resource = [
        aws_sqs_queue.appointment_events.arn,
        aws_sqs_queue.rag_processing.arn,
      ]
    }]
  })
}

# ─── health-service ───────────────────────────────────────────────────────────
resource "aws_iam_role" "sa_health_service" {
  name = "medilink-sa-health-service"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider}:sub" = "system:serviceaccount:medilink:sa-health-service"
          "${local.oidc_provider}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "sa_health_service" {
  name   = "medilink-sa-health-service-policy"
  role   = aws_iam_role.sa_health_service.id
  policy = data.aws_iam_policy_document.common_sa_policy.json
}

# ─── document-service ─────────────────────────────────────────────────────────
resource "aws_iam_role" "sa_document_service" {
  name = "medilink-sa-document-service"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider}:sub" = "system:serviceaccount:medilink:sa-document-service"
          "${local.oidc_provider}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "sa_document_service" {
  name   = "medilink-sa-document-service-policy"
  role   = aws_iam_role.sa_document_service.id
  policy = data.aws_iam_policy_document.common_sa_policy.json
}

resource "aws_iam_role_policy" "sa_document_s3" {
  name = "medilink-sa-document-s3"
  role = aws_iam_role.sa_document_service.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3Objects"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        Resource = "${module.documents_bucket.s3_bucket_arn}/*"
      },
      {
        Sid      = "S3List"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = module.documents_bucket.s3_bucket_arn
      }
    ]
  })
}

# ─── rag-service (API-only, no workers) ───────────────────────────────────────
resource "aws_iam_role" "sa_rag_service" {
  name = "medilink-sa-rag-service"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider}:sub" = "system:serviceaccount:medilink:sa-rag-service"
          "${local.oidc_provider}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "sa_rag_service" {
  name   = "medilink-sa-rag-service-policy"
  role   = aws_iam_role.sa_rag_service.id
  policy = data.aws_iam_policy_document.common_sa_policy.json
}

resource "aws_iam_role_policy" "sa_rag_bedrock" {
  name = "medilink-sa-rag-bedrock"
  role = aws_iam_role.sa_rag_service.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "BedrockInvoke"
      Effect = "Allow"
      Action = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:ApplyGuardrail",
      ]
      Resource = [
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
        "arn:aws:bedrock:us-east-1:${data.aws_caller_identity.current.account_id}:guardrail/*",
      ]
    }]
  })
}

# ─── rag-worker (SQS consumer + Textract + embeddings) ────────────────────────
resource "aws_iam_role" "sa_rag_worker" {
  name = "medilink-sa-rag-worker"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider}:sub" = "system:serviceaccount:medilink:sa-rag-worker"
          "${local.oidc_provider}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "sa_rag_worker_base" {
  name   = "medilink-sa-rag-worker-base"
  role   = aws_iam_role.sa_rag_worker.id
  policy = data.aws_iam_policy_document.common_sa_policy.json
}

resource "aws_iam_role_policy" "sa_rag_worker_sqs" {
  name = "medilink-sa-rag-worker-sqs"
  role = aws_iam_role.sa_rag_worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "SQSConsume"
      Effect = "Allow"
      Action = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl",
      ]
      Resource = [
        aws_sqs_queue.rag_processing.arn,
        aws_sqs_queue.rag_processing_dlq.arn,
      ]
    }]
  })
}

resource "aws_iam_role_policy" "sa_rag_worker_textract" {
  name = "medilink-sa-rag-worker-textract"
  role = aws_iam_role.sa_rag_worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TextractSync"
        Effect = "Allow"
        Action = [
          "textract:DetectDocumentText",
          "textract:AnalyzeDocument",
          "textract:StartDocumentTextDetection",
          "textract:GetDocumentTextDetection",
        ]
        Resource = "*"
      },
      {
        Sid    = "S3ForTextract"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = "${module.documents_bucket.s3_bucket_arn}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "sa_rag_worker_bedrock" {
  name = "medilink-sa-rag-worker-bedrock"
  role = aws_iam_role.sa_rag_worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "BedrockEmbeddings"
      Effect = "Allow"
      Action = ["bedrock:InvokeModel"]
      Resource = [
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
      ]
    }]
  })
}

# ─── sa-keda: KEDA operator IRSA (reads SQS queue depth, no authenticationRef) ─
resource "aws_iam_role" "sa_keda" {
  name = "medilink-sa-keda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider}:sub" = "system:serviceaccount:keda:keda-operator"
          "${local.oidc_provider}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "sa_keda" {
  name = "medilink-sa-keda-policy"
  role = aws_iam_role.sa_keda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "SQSMetrics"
      Effect = "Allow"
      Action = [
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl",
      ]
      Resource = [aws_sqs_queue.rag_processing.arn]
    }]
  })
}
