resource "aws_sns_topic" "appointment_notifications" {
  name              = "medilink-appointment-notifications"
  kms_master_key_id = aws_kms_key.medilink.arn

  tags = { Name = "medilink-sns-notifications" }
}

# Subscribing the default administrative email
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.appointment_notifications.arn
  protocol  = "email"
  endpoint  = "notifications@medilink.com"
}
