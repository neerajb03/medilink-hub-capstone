# --- External Web Application Firewall (WAF) ---
resource "aws_wafv2_web_acl" "waf" {
  name        = "medilink-production-waf"
  description = "Protects frontend web interface from malicious injection and bots"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  # AWS Managed Common Rule Set
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"

        # Prevent WAF from blocking file uploads (which are > 8KB and binary)
        rule_action_override {
          name = "SizeRestrictions_BODY"
          action_to_use {
            count {}
          }
        }
        rule_action_override {
          name = "CrossSiteScripting_BODY"
          action_to_use {
            count {}
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesCommonRuleSetMetric"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "medilinkWafMetric"
    sampled_requests_enabled   = true
  }
}

# --- External Public Load Balancer ---
resource "aws_lb" "external" {
  name               = "medilink-external-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.external_alb.id]
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]
  tags               = { Name = "medilink-external-alb" }
}

# Connect WAF to External Load Balancer
resource "aws_wafv2_web_acl_association" "external_lb" {
  resource_arn = aws_lb.external.arn
  web_acl_arn  = aws_wafv2_web_acl.waf.arn
}

# --- Target Groups ---
# Frontend Target Group
resource "aws_lb_target_group" "frontend" {
  name        = "medilink-frontend-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"

  health_check {
    path                = "/"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 3
    unhealthy_threshold = 3
    matcher             = "200-399"
  }
}

# --- Listeners & Routing Rules (External) ---
resource "aws_lb_listener" "external_http" {
  load_balancer_arn = aws_lb.external.arn
  port              = "80"
  protocol          = "HTTP"

  # Default: Forward all traffic to the frontend application
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}

# Domain-Based Routing Example (documentation fixed response)
# This demonstrates domain-based routing: requests to docs.yourdomain.com
# return a styled HTML page. Replace with your actual domain as needed.
resource "aws_lb_listener_rule" "domain_docs_example" {
  listener_arn = aws_lb_listener.external_http.arn
  priority     = 200

  action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/html"
      message_body = <<HTML
<!DOCTYPE html>
<html>
<head>
  <title>MediLink Hub - API Documentation</title>
  <style>
    body { background: #0b0f19; color: #f3f4f6; font-family: system-ui, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
    .card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 40px; max-width: 480px; text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.5); backdrop-filter: blur(10px); }
    h1 { color: #6366f1; font-weight: 700; margin-top: 0; }
    p { line-height: 1.6; color: #9ca3af; }
    .footer { margin-top: 24px; font-size: 0.8rem; color: #4b5563; }
  </style>
</head>
<body>
  <div class="card">
    <h1>MediLink Hub API Documentation</h1>
    <p>Welcome to the MediLink Hub API. This is a domain-based routing example using a fixed response.</p>
    <div class="footer">MediLink Cloud Operations Team</div>
  </div>
</body>
</html>
HTML
      status_code  = "200"
    }
  }

  # Example: domain-based routing — requests to docs.yourdomain.com show this page
  condition {
    host_header {
      values = ["docs.yourdomain.com"]
    }
  }
}

# --- Internal Private Load Balancer ---
resource "aws_lb" "internal" {
  name               = "medilink-internal-alb"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.internal_alb.id]
  subnets            = [aws_subnet.private_back_a.id, aws_subnet.private_back_b.id]
  tags               = { Name = "medilink-internal-alb" }
}

# --- Microservices Target Groups ---
resource "aws_lb_target_group" "user_service" {
  name        = "medilink-user-tg"
  port        = 8001
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"
  health_check {
    path = "/health"
    port = "8001"
  }
}

resource "aws_lb_target_group" "appointment_service" {
  name        = "medilink-appointment-tg"
  port        = 8002
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"
  health_check {
    path = "/health"
    port = "8002"
  }
}

resource "aws_lb_target_group" "health_service" {
  name        = "medilink-health-tg"
  port        = 8003
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"
  health_check {
    path = "/health"
    port = "8003"
  }
}

resource "aws_lb_target_group" "document_service" {
  name        = "medilink-document-tg"
  port        = 8004
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"
  health_check {
    path = "/health"
    port = "8004"
  }
}

# --- Internal Listener & Path-Based Routing ---
resource "aws_lb_listener" "internal_http" {
  load_balancer_arn = aws_lb.internal.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      message_body = "{\"error\": \"Invalid microservice API path request\"}"
      status_code  = "404"
    }
  }
}

# User Service Path Rule
resource "aws_lb_listener_rule" "users" {
  listener_arn = aws_lb_listener.internal_http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.user_service.arn
  }

  condition {
    path_pattern {
      values = ["/api/users/*", "/users/*", "/login", "/register", "/me"]
    }
  }
}

# Appointment Service Path Rule
resource "aws_lb_listener_rule" "appointments" {
  listener_arn = aws_lb_listener.internal_http.arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.appointment_service.arn
  }

  condition {
    path_pattern {
      values = ["/api/appointments/*", "/appointments/*", "/appointments"]
    }
  }
}

# Health Service Path Rule
resource "aws_lb_listener_rule" "health" {
  listener_arn = aws_lb_listener.internal_http.arn
  priority     = 30

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.health_service.arn
  }

  condition {
    path_pattern {
      values = ["/health-records", "/health-records/*", "/chat", "/chat/*"]
    }
  }
}

# Document Service Path Rule
resource "aws_lb_listener_rule" "documents" {
  listener_arn = aws_lb_listener.internal_http.arn
  priority     = 40

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.document_service.arn
  }

  condition {
    path_pattern {
      values = ["/api/documents/*", "/documents/*", "/documents"]
    }
  }
}
