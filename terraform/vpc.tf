locals {
  az_a = "us-east-1a"
  az_b = "us-east-1b"
}

# --- VPC ---
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "medilink-vpc" }
}

# --- Internet Gateway ---
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "medilink-igw" }
}

# --- Subnets ---
# Public Subnets (Bastion, NAT Gateways)
resource "aws_subnet" "public_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = local.az_a
  map_public_ip_on_launch = true
  tags = {
    Name                                        = "medilink-public-1a"
    "kubernetes.io/cluster/medilink-eks"        = "shared"
    "kubernetes.io/role/elb"                    = "1"
  }
}

resource "aws_subnet" "public_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = local.az_b
  map_public_ip_on_launch = true
  tags = {
    Name                                        = "medilink-public-1b"
    "kubernetes.io/cluster/medilink-eks"        = "shared"
    "kubernetes.io/role/elb"                    = "1"
  }
}

# Private Subnets (Frontend App)
resource "aws_subnet" "private_front_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = local.az_a
  tags              = { Name = "medilink-private-front-1a" }
}

resource "aws_subnet" "private_front_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.4.0/24"
  availability_zone = local.az_b
  tags              = { Name = "medilink-private-front-1b" }
}

# Private Subnets (Backend APIs)
resource "aws_subnet" "private_back_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.5.0/24"
  availability_zone = local.az_a
  tags = {
    Name                                        = "medilink-private-back-1a"
    "kubernetes.io/cluster/medilink-eks"        = "shared"
    "kubernetes.io/role/internal-elb"           = "1"
  }
}

resource "aws_subnet" "private_back_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.6.0/24"
  availability_zone = local.az_b
  tags = {
    Name                                        = "medilink-private-back-1b"
    "kubernetes.io/cluster/medilink-eks"        = "shared"
    "kubernetes.io/role/internal-elb"           = "1"
  }
}

# Private Subnets (RDS Databases)
resource "aws_subnet" "private_db_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.7.0/24"
  availability_zone = local.az_a
  tags              = { Name = "medilink-private-db-1a" }
}

resource "aws_subnet" "private_db_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.8.0/24"
  availability_zone = local.az_b
  tags              = { Name = "medilink-private-db-1b" }
}

# --- NAT Gateways (High Availability) ---
resource "aws_eip" "nat_a" {
  domain = "vpc"
}

resource "aws_eip" "nat_b" {
  domain = "vpc"
}

resource "aws_nat_gateway" "nat_a" {
  allocation_id = aws_eip.nat_a.id
  subnet_id     = aws_subnet.public_a.id
  tags          = { Name = "medilink-nat-1a" }
}

resource "aws_nat_gateway" "nat_b" {
  allocation_id = aws_eip.nat_b.id
  subnet_id     = aws_subnet.public_b.id
  tags          = { Name = "medilink-nat-1b" }
}

# --- Route Tables & Associations ---
# Public Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = { Name = "medilink-public-rt" }
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

# Private Route Table A (via NAT A)
resource "aws_route_table" "private_a" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat_a.id
  }
  tags = { Name = "medilink-private-rt-1a" }
}

resource "aws_route_table_association" "front_a" {
  subnet_id      = aws_subnet.private_front_a.id
  route_table_id = aws_route_table.private_a.id
}

resource "aws_route_table_association" "back_a" {
  subnet_id      = aws_subnet.private_back_a.id
  route_table_id = aws_route_table.private_a.id
}

# Private Route Table B (via NAT B)
resource "aws_route_table" "private_b" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat_b.id
  }
  tags = { Name = "medilink-private-rt-1b" }
}

resource "aws_route_table_association" "front_b" {
  subnet_id      = aws_subnet.private_front_b.id
  route_table_id = aws_route_table.private_b.id
}

resource "aws_route_table_association" "back_b" {
  subnet_id      = aws_subnet.private_back_b.id
  route_table_id = aws_route_table.private_b.id
}

# DB subnets — isolated (no NAT route needed; RDS does not initiate outbound traffic)
resource "aws_route_table" "private_db" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "medilink-private-rt-db" }
}

resource "aws_route_table_association" "db_a" {
  subnet_id      = aws_subnet.private_db_a.id
  route_table_id = aws_route_table.private_db.id
}

resource "aws_route_table_association" "db_b" {
  subnet_id      = aws_subnet.private_db_b.id
  route_table_id = aws_route_table.private_db.id
}
