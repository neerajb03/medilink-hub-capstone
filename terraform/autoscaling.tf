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

  # No custom AMI needed — everything is pulled from GitHub at boot time
  # (same approach as the backend launch template)

  user_data = base64encode(<<-EOF
              #!/bin/bash
              echo "=== MediLink Frontend Bootstrap ==="
              date

              # Install Node.js 18 if not present
              if ! which node > /dev/null 2>&1; then
                curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
                apt-get install -y nodejs
              fi

              # Clone latest code from GitHub (force clean clone)
              cd /home/ubuntu
              rm -rf medilink-hub
              git clone https://github.com/neerajb03/medilink-hub.git
              cd medilink-hub/frontend

              # Set Internal ALB DNS for Vite proxy (server-side routing to backends)
              export INTERNAL_ALB_DNS="http://${aws_lb.internal.dns_name}"
              echo "INTERNAL_ALB_DNS=$INTERNAL_ALB_DNS"

              # Install dependencies and start
              npm install
              nohup npm run dev -- --host 0.0.0.0 --port 3000 > /var/log/frontend.log 2>&1 &
              echo "Frontend started with PID $!"
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
              # Removed manual exec redirect so output goes to standard cloud-init-output.log (visible in EC2 System Log)
              echo "=== MediLink Backend Bootstrap ==="
              date

              # Install dependencies if missing
              apt-get update
              which git  || apt-get install -y git
              which pip3 || apt-get install -y python3-pip python3-venv
              which psql || apt-get install -y postgresql-client
              which jq   || apt-get install -y jq
              # Install AWS CLI (not pre-installed on Ubuntu AMIs)
              which aws  || apt-get install -y awscli

              # Clone latest code from GitHub (Force clean clone)
              cd /home/ubuntu
              rm -rf medilink-hub
              git clone https://github.com/neerajb03/medilink-hub.git
              cd medilink-hub

              # Create individual databases using Python/boto3 to avoid
              # shell quoting issues with special characters in the RDS password
              python3 -c "
import subprocess, json, os, sys
try:
    import boto3
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'boto3'])
    import boto3
client = boto3.client('secretsmanager', region_name='us-east-1')
secret = json.loads(client.get_secret_value(SecretId='${aws_secretsmanager_secret.db_credentials.id}')['SecretString'])
os.environ['PGPASSWORD'] = secret['password']
host = '${aws_db_instance.postgres.address}'
for db in ['user_db', 'appointment_db', 'health_db', 'document_db']:
    r = subprocess.run(['psql', '-h', host, '-p', '5432', '-U', secret['username'], '-d', 'postgres', '-c', f'CREATE DATABASE {db};'], capture_output=True, text=True)
    print(f'{db}: Created' if r.returncode == 0 else f'{db}: {r.stderr.strip()}')
"

              export S3_BUCKET_NAME="${aws_s3_bucket.documents.bucket}"
              export S3_ENDPOINT=""
              export AWS_DEFAULT_REGION="us-east-1"
              export SQS_QUEUE_URL="${aws_sqs_queue.appointment_events.url}"

              # Setup Python Virtual Environment
              cd /home/ubuntu/medilink-hub
              python3 -m venv venv
              source venv/bin/activate

              # Start each service (credentials fetched from Secrets Manager via aws_utils.py)
              echo "Starting user-service..."
              cd /home/ubuntu/medilink-hub/user-service
              pip install -r requirements.txt
              nohup uvicorn main:app --host 0.0.0.0 --port 8001 > /var/log/user-service.log 2>&1 &

              echo "Starting appointment-service..."
              cd /home/ubuntu/medilink-hub/appointment-service
              pip install -r requirements.txt
              python3 -m alembic upgrade head
              nohup uvicorn main:app --host 0.0.0.0 --port 8002 > /var/log/appointment-service.log 2>&1 &

              echo "Starting health-service..."
              cd /home/ubuntu/medilink-hub/health-service
              pip install -r requirements.txt
              python3 -m alembic upgrade head
              nohup uvicorn main:app --host 0.0.0.0 --port 8003 > /var/log/health-service.log 2>&1 &

              echo "Starting document-service..."
              cd /home/ubuntu/medilink-hub/document-service
              pip install -r requirements.txt
              python3 -m alembic upgrade head
              nohup uvicorn main:app --host 0.0.0.0 --port 8004 > /var/log/document-service.log 2>&1 &

              echo "All services started."
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
  health_check_grace_period = 600

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
  health_check_grace_period = 900

  tag {
    key                 = "Name"
    value               = "medilink-backend-server"
    propagate_at_launch = true
  }
}

# --- Dynamic Target Tracking Auto Scaling ---
resource "aws_autoscaling_policy" "backend_cpu_tracking" {
  name                   = "medilink-backend-cpu-tracking"
  autoscaling_group_name = aws_autoscaling_group.backend.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 50.0
  }
}
