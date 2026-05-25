# --- AMI Placeholders (To be replaced by custom AMIs constructed in Step 2) ---
# Feel free to update with real AMIs built via packer or manual console setup.
variable "frontend_ami_id" {
  type    = string
  default = "ami-0c7217cdde317cfec" # Example base Amazon Linux 2023 or custom AMI
}

variable "backend_ami_id" {
  type    = string
  default = "ami-0c7217cdde317cfec" # Example base Amazon Linux 2023 or custom AMI
}

# Keypair name
variable "key_name" {
  type    = string
  default = "neerajvmkey"
}

# --- Launch Templates ---

# Frontend Launch Template
resource "aws_launch_template" "frontend" {
  name_prefix   = "medilink-frontend-"
  image_id      = var.frontend_ami_id
  instance_type = "t3.micro"
  key_name      = var.key_name

  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [aws_security_group.frontend_asg.id]
  }

  user_data = base64encode(<<-EOF
              #!/bin/bash
              set -e
              echo "Starting MediLink Frontend..."

              # Clone latest code from GitHub
              cd /home/ec2-user
              if [ -d "medilink-hub" ]; then
                cd medilink-hub && git pull origin main
              else
                git clone https://github.com/neerajb03/medilink-hub.git
                cd medilink-hub
              fi

              # Install frontend dependencies
              cd frontend
              npm install

              # Set Internal ALB DNS for Vite proxy (server-side routing to backends)
              export INTERNAL_ALB_DNS="http://${aws_lb.internal.dns_name}"
              nohup npm run dev -- --host 0.0.0.0 --port 3000 &
              EOF
  )

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "medilink-frontend-asg-instance" }
  }
}

# Backend Launch Template
resource "aws_launch_template" "backend" {
  name_prefix   = "medilink-backend-"
  image_id      = var.backend_ami_id
  instance_type = "t3.micro"
  key_name      = var.key_name

  iam_instance_profile {
    name = aws_iam_instance_profile.backend.name
  }

  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [aws_security_group.backend_asg.id]
  }

  user_data = base64encode(<<-EOF
              #!/bin/bash
              set -e
              echo "Starting MediLink microservices..."

              # Clone latest code from GitHub
              cd /home/ec2-user
              if [ -d "medilink-hub" ]; then
                cd medilink-hub && git pull origin main
              else
                git clone https://github.com/neerajb03/medilink-hub.git
                cd medilink-hub
              fi

              export DATABASE_URL="postgresql+asyncpg://dbadmin:ProductionStrongPassword123!@${aws_db_instance.postgres.endpoint}/"
              export S3_BUCKET_NAME="${aws_s3_bucket.documents.bucket}"
              export S3_ENDPOINT="" # Leave empty for native AWS S3
              export AWS_DEFAULT_REGION="us-east-1"
              export JWT_SECRET="supersecret"

              # Install dependencies and start each service
              cd /home/ec2-user/medilink-hub/user-service && pip install -r requirements.txt && nohup uvicorn main:app --host 0.0.0.0 --port 8001 &
              cd /home/ec2-user/medilink-hub/appointment-service && pip install -r requirements.txt && nohup uvicorn main:app --host 0.0.0.0 --port 8002 &
              cd /home/ec2-user/medilink-hub/health-service && pip install -r requirements.txt && nohup uvicorn main:app --host 0.0.0.0 --port 8003 &
              cd /home/ec2-user/medilink-hub/document-service && pip install -r requirements.txt && nohup uvicorn main:app --host 0.0.0.0 --port 8004 &
              EOF
  )

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "medilink-backend-asg-instance" }
  }
}

# --- Auto Scaling Groups ---

# Frontend Auto Scaling Group (Private subnets AZ A & B)
resource "aws_autoscaling_group" "frontend" {
  name                = "medilink-frontend-asg"
  vpc_zone_identifier = [aws_subnet.private_front_a.id, aws_subnet.private_front_b.id]
  target_group_arns   = [aws_lb_target_group.frontend.arn]

  min_size         = 1
  max_size         = 2
  desired_capacity = 1

  launch_template {
    id      = aws_launch_template.frontend.id
    version = "$Latest"
  }

  health_check_type         = "ELB"
  health_check_grace_period = 300

  tag {
    key                 = "Name"
    value               = "medilink-frontend-server"
    propagate_at_launch = true
  }
}

# Backend Auto Scaling Group (Private subnets AZ A & B)
resource "aws_autoscaling_group" "backend" {
  name                = "medilink-backend-asg"
  vpc_zone_identifier = [aws_subnet.private_back_a.id, aws_subnet.private_back_b.id]
  
  target_group_arns   = [
    aws_lb_target_group.user_service.arn,
    aws_lb_target_group.appointment_service.arn,
    aws_lb_target_group.health_service.arn,
    aws_lb_target_group.document_service.arn
  ]

  min_size         = 1
  max_size         = 2
  desired_capacity = 1

  launch_template {
    id      = aws_launch_template.backend.id
    version = "$Latest"
  }

  health_check_type         = "ELB"
  health_check_grace_period = 300

  tag {
    key                 = "Name"
    value               = "medilink-backend-server"
    propagate_at_launch = true
  }
}
