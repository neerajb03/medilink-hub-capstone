# EC2 ALBs retired — ingress is now handled by the AWS Load Balancer Controller
# (lb_controller.tf) provisioning an ALB from the KGateway Gateway resource.
# WAF is attached via annotation on the Gateway Service:
#   service.beta.kubernetes.io/aws-load-balancer-wafv2-acl-arn: <regional_waf_arn output>
# Path routing lives in helm/medilink/templates/kgateway/httproutes.yaml
