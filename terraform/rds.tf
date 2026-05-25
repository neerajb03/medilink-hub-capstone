# --- DB Subnet Group ---
resource "aws_db_subnet_group" "rds" {
  name       = "medilink-db-subnet-group"
  subnet_ids = [aws_subnet.private_db_a.id, aws_subnet.private_db_b.id]
  tags       = { Name = "medilink-db-subnet-group" }
}

# --- Multi-AZ DB Cluster (High Availability Setup) ---
resource "aws_db_instance" "postgres" {
  identifier             = "medilink-production-db"
  allocated_storage      = 20
  max_allocated_storage  = 100
  db_name                = "postgres" # Initial DB
  engine                 = "postgres"
  engine_version         = "18.3"
  instance_class         = "db.t4g.micro"
  username               = "dbadmin"
  password               = "ProductionStrongPassword123!" # Ideally fetched from SSM Parameter Store/Secrets Manager
  db_subnet_group_name   = aws_db_subnet_group.rds.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  multi_az               = false # Single AZ for cost efficiency on db.t4g.micro
  skip_final_snapshot    = true

  tags = { Name = "medilink-rds-postgres" }
}
