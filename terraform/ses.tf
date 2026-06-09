# --- Amazon SES Email Identity ---

resource "aws_ses_email_identity" "admin" {
  email = "medilinkhub.team@gmail.com"
}
