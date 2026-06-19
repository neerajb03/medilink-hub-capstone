# --- DB Subnet Group ---
resource "aws_db_subnet_group" "rds" {
  name       = "medilink-db-subnet-group"
  subnet_ids = [aws_subnet.private_db_a.id, aws_subnet.private_db_b.id]
  tags       = { Name = "medilink-db-subnet-group" }
}

# --- Generate Random Password ---
resource "random_password" "db_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# --- Multi-AZ DB Cluster (High Availability Setup) ---
resource "aws_db_instance" "postgres" {
  identifier             = "medilink-production-db"
  allocated_storage      = 20
  max_allocated_storage  = 100
  db_name                = "postgres" # Initial DB
  engine                 = "postgres"
  instance_class         = "db.t4g.micro"
  username               = "dbadmin"
  password               = random_password.db_password.result
  db_subnet_group_name   = aws_db_subnet_group.rds.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  multi_az                = false # Single AZ for cost efficiency (production would enable Multi-AZ)
  skip_final_snapshot     = true
  storage_encrypted       = true
  kms_key_id              = aws_kms_key.medilink.arn
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  tags = { Name = "medilink-rds-postgres" }
}
