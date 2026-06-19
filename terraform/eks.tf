module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "medilink-eks"
  cluster_version = "1.30"

  vpc_id                   = aws_vpc.main.id
  subnet_ids               = [aws_subnet.private_back_a.id, aws_subnet.private_back_b.id]
  control_plane_subnet_ids = [aws_subnet.private_back_a.id, aws_subnet.private_back_b.id]

  cluster_endpoint_public_access = true

  enable_cluster_creator_admin_permissions = true

  enable_irsa = true

  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = aws_iam_role.ebs_csi.arn
    }
  }

  eks_managed_node_groups = {
    general = {
      name           = "medilink-node-group"
      min_size       = 2
      max_size       = 6
      desired_size   = 3
      instance_types = ["t3.medium"]

      iam_role_additional_policies = {
        AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
      }

      labels = {
        role = "general"
      }
    }
  }

  node_security_group_additional_rules = {
    ingress_cluster_all = {
      description                   = "Allow cluster to node all ports"
      protocol                      = "-1"
      from_port                     = 0
      to_port                       = 0
      type                          = "ingress"
      source_cluster_security_group = true
    }
    egress_all = {
      description = "Node all egress"
      protocol    = "-1"
      from_port   = 0
      to_port     = 0
      type        = "egress"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  tags = {
    Name = "medilink-eks"
  }
}

# EBS CSI Driver IRSA role (required by the addon)
resource "aws_iam_role" "ebs_csi" {
  name = "medilink-ebs-csi-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = module.eks.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${module.eks.oidc_provider}:sub" = "system:serviceaccount:kube-system:ebs-csi-controller-sa"
          "${module.eks.oidc_provider}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role       = aws_iam_role.ebs_csi.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

# Allow EKS nodes to pull from ECR
resource "aws_iam_role_policy_attachment" "node_ecr" {
  for_each = module.eks.eks_managed_node_groups

  role       = each.value.iam_role_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Allow EKS nodes to write CloudWatch metrics (for Container Insights)
resource "aws_iam_role_policy_attachment" "node_cloudwatch" {
  for_each = module.eks.eks_managed_node_groups

  role       = each.value.iam_role_name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# Allow RDS SG to accept connections from EKS node SG
resource "aws_security_group_rule" "rds_from_eks_nodes" {
  type                     = "ingress"
  description              = "PostgreSQL from EKS node group"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = module.eks.node_security_group_id
}
