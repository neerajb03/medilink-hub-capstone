# --- CloudWatch Log Groups ---
locals {
  log_groups = [
    "/medilink/backend/user-service",
    "/medilink/backend/appointment-service",
    "/medilink/backend/health-service",
    "/medilink/backend/document-service",
    "/medilink/backend/rag-service",
    "/medilink/backend/rag-worker",
    "/aws/lambda/medilink-notification-worker",
    "/medilink/aiops/pod-crash-diagnosis",
  ]
}

resource "aws_cloudwatch_log_group" "medilink" {
  for_each          = toset(local.log_groups)
  name              = each.key
  retention_in_days = 30
  kms_key_id        = aws_kms_key.medilink.arn

  tags = { Name = "medilink-log-group" }
}

# --- Operational Alarms Notification ---
resource "aws_sns_topic" "ops_alarms" {
  name              = "medilink-ops-alarms"
  kms_master_key_id = aws_kms_key.medilink.arn
}

resource "aws_sns_topic_subscription" "ops_email" {
  topic_arn = aws_sns_topic.ops_alarms.arn
  protocol  = "email"
  endpoint  = "medilinkhub.team@gmail.com" # Placeholder for the ops team
}

# --- MVP CloudWatch Alarms ---

# 1. KGateway ALB 5xx Errors — dimension is set after Phase 2 via var.gateway_alb_dns
# The LB Controller creates this ALB; its ARN suffix is not known at Terraform apply time.
# Alarm is wired up in Phase 12 (AIOps) after the ALB exists.
# Placeholder alarm on the SQS RAG DLQ instead:
resource "aws_cloudwatch_metric_alarm" "rag_dlq_depth" {
  alarm_name          = "medilink-rag-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Maximum"
  threshold           = "0"
  alarm_description   = "RAG document processing is failing — messages in DLQ."
  alarm_actions       = [aws_sns_topic.ops_alarms.arn]

  dimensions = {
    QueueName = aws_sqs_queue.rag_processing_dlq.name
  }
}

# 2. SQS Dead Letter Queue Size (Notifications are silently failing)
resource "aws_cloudwatch_metric_alarm" "sqs_dlq_depth" {
  alarm_name          = "medilink-sqs-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Maximum"
  threshold           = "0" # Alert if ANY messages end up in the DLQ
  alarm_description   = "Appointment notifications are failing and moving to DLQ."
  alarm_actions       = [aws_sns_topic.ops_alarms.arn]

  dimensions = {
    QueueName = aws_sqs_queue.appointment_events_dlq.name
  }
}
