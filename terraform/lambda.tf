# --- IAM Role for Lambda ---
resource "aws_iam_role" "lambda_worker" {
  name = "medilink-notification-lambda-role"
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

# Permissions: CloudWatch Logs, SNS Publish, SQS Receive/Delete, KMS Decrypt
resource "aws_iam_role_policy" "lambda_worker_policy" {
  name = "medilink-lambda-execution-policy"
  role = aws_iam_role.lambda_worker.id

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
        Resource = "arn:aws:logs:us-east-1:*:log-group:/aws/lambda/*"
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.appointment_events.arn
      },
      {
        Effect = "Allow"
        Action = "ses:SendEmail"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.medilink.arn
      }
    ]
  })
}

# --- Zip Lambda Code ---
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../notification_worker.py"
  output_path = "${path.module}/notification_worker.zip"
}

# --- Lambda Function ---
resource "aws_lambda_function" "notification_worker" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "medilink-notification-worker"
  role             = aws_iam_role.lambda_worker.arn
  handler          = "notification_worker.lambda_handler"
  runtime          = "python3.11"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      ADMIN_EMAIL = "medilinkhub.team@gmail.com"
    }
  }

  tags = { Name = "medilink-lambda-worker" }
}

# --- SQS Trigger Mapping ---
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.appointment_events.arn
  function_name    = aws_lambda_function.notification_worker.arn
  batch_size       = 10
}
