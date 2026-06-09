output "vpc_id" {
  description = "The ID of the VPC"
  value       = aws_vpc.main.id
}

output "external_alb_dns" {
  description = "Public domain to access MediLink Hub"
  value       = aws_lb.external.dns_name
}

output "internal_alb_dns" {
  description = "Private routing endpoint for backend microservices"
  value       = aws_lb.internal.dns_name
}

output "rds_endpoint" {
  description = "RDS Connection Endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "s3_bucket_name" {
  description = "S3 Medical Files Bucket Name"
  value       = module.documents_bucket.s3_bucket_id
}

output "kms_key_arn" {
  description = "KMS key ARN used for encryption"
  value       = aws_kms_key.medilink.arn
}

output "secrets_manager_db_arn" {
  description = "Secrets Manager ARN for DB credentials"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "sns_topic_arn" {
  description = "SNS topic ARN for appointment notifications"
  value       = aws_sns_topic.appointment_notifications.arn
}

output "sqs_queue_url" {
  description = "SQS queue URL for appointment events"
  value       = aws_sqs_queue.appointment_events.url
}

output "ops_alarm_topic_arn" {
  description = "SNS topic ARN for operational alarms"
  value       = aws_sns_topic.ops_alarms.arn
}
