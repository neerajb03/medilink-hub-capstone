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
  value       = aws_s3_bucket.documents.bucket
}
