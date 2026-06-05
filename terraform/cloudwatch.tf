# --- CloudWatch Log Groups ---
locals {
  log_groups = [
    "/medilink/backend/user-service",
    "/medilink/backend/appointment-service",
    "/medilink/backend/health-service",
    "/medilink/backend/document-service",
    "/medilink/backend/cloud-init",      # For EC2 bootstrap logs
    "/aws/lambda/medilink-notification-worker"
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
  endpoint  = "ops@medilink.com" # Placeholder for the ops team
}

# --- MVP CloudWatch Alarms ---

# 1. External ALB 5xx Errors (API is down)
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "medilink-alb-5xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Sum"
  threshold           = "10" # Alert if more than 10 5xx errors in 2 minutes
  alarm_description   = "API is returning 5xx errors to users."
  alarm_actions       = [aws_sns_topic.ops_alarms.arn]
  
  dimensions = {
    LoadBalancer = aws_lb.external.arn_suffix
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
