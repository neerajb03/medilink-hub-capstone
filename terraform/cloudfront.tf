variable "gateway_alb_dns" {
  description = "DNS name of the ALB created by the KGateway Gateway resource. Run 'kubectl get svc -n kube-system' after Phase 2 to get this value, then re-run terraform apply."
  type        = string
  default     = ""
}

resource "random_password" "cloudfront_auth" {
  length  = 32
  special = false
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

# CloudFront is created only once the KGateway ALB DNS is known.
# Set var.gateway_alb_dns after Phase 2 and re-apply.
resource "aws_cloudfront_distribution" "main" {
  count = var.gateway_alb_dns != "" ? 1 : 0

  enabled         = true
  is_ipv6_enabled = true
  price_class     = "PriceClass_200"
  web_acl_id      = aws_wafv2_web_acl.global_waf.arn

  origin {
    domain_name = var.gateway_alb_dns
    origin_id   = "KGatewayALB"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    custom_header {
      name  = "X-CloudFront-Auth"
      value = random_password.cloudfront_auth.result
    }
  }

  default_cache_behavior {
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "KGatewayALB"
    viewer_protocol_policy = "redirect-to-https"
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

output "cloudfront_domain_name" {
  description = "CloudFront domain (empty until var.gateway_alb_dns is set after Phase 2)"
  value       = length(aws_cloudfront_distribution.main) > 0 ? aws_cloudfront_distribution.main[0].domain_name : "Set var.gateway_alb_dns and re-apply"
}
