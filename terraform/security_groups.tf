# --- Bastion Security Group ---
resource "aws_security_group" "bastion" {
  name        = "medilink-bastion-sg"
  description = "Allow inbound SSH access to admin host"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH administrative access"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "medilink-bastion-sg" }
}

# --- External Load Balancer Security Group ---
resource "aws_security_group" "external_alb" {
  name        = "medilink-external-alb-sg"
  description = "Allows public web traffic to external load balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Public HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Public HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "medilink-external-alb-sg" }
}

# --- Frontend Web Security Group ---
resource "aws_security_group" "frontend_asg" {
  name        = "medilink-frontend-sg"
  description = "Allows traffic only from external load balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.external_alb.id]
  }

  ingress {
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "medilink-frontend-sg" }
}

# --- Internal Load Balancer Security Group ---
resource "aws_security_group" "internal_alb" {
  name        = "medilink-internal-alb-sg"
  description = "Allows traffic from frontend hosts to backend services"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.frontend_asg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "medilink-internal-alb-sg" }
}

resource "aws_security_group_rule" "internal_alb_from_backend" {
  type                     = "ingress"
  from_port                = 80
  to_port                  = 80
  protocol                 = "tcp"
  security_group_id        = aws_security_group.internal_alb.id
  source_security_group_id = aws_security_group.backend_asg.id
}

# --- Backend API Security Group ---
resource "aws_security_group" "backend_asg" {
  name        = "medilink-backend-sg"
  description = "Allows traffic from internal load balancer and admin host"
  vpc_id      = aws_vpc.main.id

  # Microservices Ports
  ingress {
    description     = "User service endpoint"
    from_port       = 8001
    to_port         = 8001
    protocol        = "tcp"
    security_groups = [aws_security_group.internal_alb.id]
  }

  ingress {
    description     = "Appointment service endpoint"
    from_port       = 8002
    to_port         = 8002
    protocol        = "tcp"
    security_groups = [aws_security_group.internal_alb.id]
  }

  ingress {
    description     = "Health records service endpoint"
    from_port       = 8003
    to_port         = 8003
    protocol        = "tcp"
    security_groups = [aws_security_group.internal_alb.id]
  }

  ingress {
    description     = "Document management service endpoint"
    from_port       = 8004
    to_port         = 8004
    protocol        = "tcp"
    security_groups = [aws_security_group.internal_alb.id]
  }

  ingress {
    description     = "Administrative SSH access"
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "medilink-backend-sg" }
}

# --- RDS Security Group ---
resource "aws_security_group" "rds" {
  name        = "medilink-rds-sg"
  description = "Allows database connections from backends and admin hosts"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL connections from backend APIs"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.backend_asg.id]
  }

  ingress {
    description     = "PostgreSQL maintenance connections from bastion host"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "medilink-rds-sg" }
}
