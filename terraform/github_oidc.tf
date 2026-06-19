locals {
  github_org  = "neerajb03" # VERIFY: must exactly match your GitHub username
  github_repo = "medilink-hub-capstone"     # the app repo that runs CI/CD
}

# --- GitHub Actions OIDC Provider ---
resource "aws_iam_openid_connect_provider" "github_actions" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = ["sts.amazonaws.com"]

  # GitHub's OIDC thumbprint (stable, retrieved from their OIDC discovery doc)
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# --- IAM Role trusted by GitHub Actions CI/CD ---
resource "aws_iam_role" "github_actions" {
  name = "medilink-github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github_actions.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          # Only main branch and PR workflows can assume this role
          "token.actions.githubusercontent.com:sub" = "repo:${local.github_org}/${local.github_repo}:*"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_actions" {
  name = "medilink-github-actions-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Push and pull images from ECR
      {
        Sid    = "ECRAuth"
        Effect = "Allow"
        Action = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:GetRepositoryPolicy",
          "ecr:DescribeRepositories",
          "ecr:ListImages",
          "ecr:DescribeImages",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
        ]
        Resource = [for repo in aws_ecr_repository.services : repo.arn]
      },
      # Update EKS deployments (ArgoCD image updater / kubectl rollout)
      {
        Sid    = "EKSDescribe"
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster",
          "eks:ListClusters",
        ]
        Resource = module.eks.cluster_arn
      },
      # Terraform state access for plan/apply in CI
      {
        Sid    = "TerraformState"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::medilink-tf-state-371454942267",
          "arn:aws:s3:::medilink-tf-state-371454942267/*",
        ]
      }
    ]
  })
}

output "github_actions_role_arn" {
  description = "ARN to paste into GitHub repo → Settings → Secrets as AWS_ROLE_ARN"
  value       = aws_iam_role.github_actions.arn
}
