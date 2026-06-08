# --- Secrets Manager for DB Credentials ---
resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "medilink/production/db-credentials"
  description             = "PostgreSQL credentials for MediLink Hub"
  kms_key_id              = aws_kms_key.medilink.arn
  recovery_window_in_days = 0

  tags = { Name = "medilink-db-secret" }
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = aws_db_instance.postgres.username
    password = aws_db_instance.postgres.password
    host     = aws_db_instance.postgres.address
    port     = aws_db_instance.postgres.port
  })
}

# --- Secrets Manager for JWT Secret ---
resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  name                    = "medilink/production/jwt-secret"
  description             = "JWT signing secret for authentication"
  kms_key_id              = aws_kms_key.medilink.arn
  recovery_window_in_days = 0

  tags = { Name = "medilink-jwt-secret" }
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = random_password.jwt_secret.result
}

# --- Secrets Manager for Hugging Face API Key ---
# Note: The actual API key should be injected manually or via CI/CD,
# this just creates the secret placeholder.
resource "aws_secretsmanager_secret" "hf_api_key" {
  name        = "medilink/production/hf-api-key"
  description             = "Hugging Face Inference API Token"
  kms_key_id              = aws_kms_key.medilink.arn
  recovery_window_in_days = 0

  tags = { Name = "medilink-hf-secret" }
}

resource "aws_secretsmanager_secret_version" "hf_api_key" {
  secret_id     = aws_secretsmanager_secret.hf_api_key.id
  secret_string = "REPLACE_ME_MANUALLY_IN_CONSOLE"
  
  lifecycle {
    ignore_changes = [secret_string]
  }
}

# --- Secrets Manager for Groq API Key ---
# Note: The actual API key should be injected manually or via CI/CD
resource "aws_secretsmanager_secret" "groq_api_key" {
  name                    = "medilink/production/groq-api-key"
  description             = "Groq API Token for Fallback LLM"
  kms_key_id              = aws_kms_key.medilink.arn
  recovery_window_in_days = 0

  tags = { Name = "medilink-groq-secret" }
}

resource "aws_secretsmanager_secret_version" "groq_api_key" {
  secret_id     = aws_secretsmanager_secret.groq_api_key.id
  secret_string = "REPLACE_ME_MANUALLY_IN_CONSOLE"
  
  lifecycle {
    ignore_changes = [secret_string]
  }
}
