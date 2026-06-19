output "vpc_id" {
  description = "The ID of the VPC"
  value       = aws_vpc.main.id
}

output "eks_cluster_name" {
  description = "EKS cluster name (use with: aws eks update-kubeconfig --name <value>)"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = module.eks.cluster_endpoint
}

output "ecr_registry" {
  description = "ECR registry URL prefix for docker push/pull"
  value       = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com"
}

output "rag_sqs_queue_url" {
  description = "SQS URL for RAG processing queue (document-service → rag-worker)"
  value       = aws_sqs_queue.rag_processing.url
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
