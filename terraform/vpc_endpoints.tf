data "aws_region" "current" {}

locals {
  services = [
    "secretsmanager",
    "sqs",
    "sns",
    "logs"
  ]
}

# --- Interface Endpoints (AWS PrivateLink) ---
resource "aws_vpc_endpoint" "private_link" {
  for_each = toset(local.services)

  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [
    aws_subnet.private_back_a.id,
    aws_subnet.private_back_b.id
  ]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "medilink-endpoint-${each.key}" }
}

# --- S3 Gateway Endpoint ---
resource "aws_vpc_endpoint" "s3_gateway" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [
    aws_route_table.private_a.id,
    aws_route_table.private_b.id
  ]

  tags = { Name = "medilink-endpoint-s3" }
}

# --- Security Group for Interface Endpoints ---
resource "aws_security_group" "vpc_endpoints" {
  name        = "medilink-vpc-endpoints-sg"
  description = "Allow inbound HTTPS from private subnets"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }
}
