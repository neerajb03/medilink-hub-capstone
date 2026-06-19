# --- RAG Processing Queue (document-service → rag-worker via KEDA) ---
resource "aws_sqs_queue" "rag_processing_dlq" {
  name                      = "medilink-rag-processing-dlq"
  kms_master_key_id         = aws_kms_key.medilink.arn
  message_retention_seconds = 1209600
  tags                      = { Name = "medilink-sqs-rag-dlq" }
}

resource "aws_sqs_queue" "rag_processing" {
  name              = "medilink-rag-processing"
  kms_master_key_id = aws_kms_key.medilink.arn

  # Must be >= rag-worker processing timeout (Textract can take 60-120s per doc)
  visibility_timeout_seconds = 300

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.rag_processing_dlq.arn
    maxReceiveCount     = 3
  })

  tags = { Name = "medilink-sqs-rag-processing" }
}

# --- Appointment Events Queue ---
# Dead Letter Queue
resource "aws_sqs_queue" "appointment_events_dlq" {
  name              = "medilink-appointment-events-dlq"
  kms_master_key_id = aws_kms_key.medilink.arn
  message_retention_seconds = 1209600 # 14 days
}

# Main SQS Queue
resource "aws_sqs_queue" "appointment_events" {
  name              = "medilink-appointment-events"
  kms_master_key_id = aws_kms_key.medilink.arn
  
  # Lambda needs Visibility Timeout > Function Timeout
  visibility_timeout_seconds = 60 

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.appointment_events_dlq.arn
    maxReceiveCount     = 3
  })

  tags = { Name = "medilink-sqs-appointments" }
}

# Lambda requires explicit permission to receive messages
data "aws_iam_policy_document" "sqs_lambda_policy" {
  statement {
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes"
    ]
    resources = [aws_sqs_queue.appointment_events.arn]
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.lambda_worker.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "lambda_policy" {
  queue_url = aws_sqs_queue.appointment_events.id
  policy    = data.aws_iam_policy_document.sqs_lambda_policy.json
}
