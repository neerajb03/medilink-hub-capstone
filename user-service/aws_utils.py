"""Utility to fetch secrets from AWS Secrets Manager at runtime."""
import json
import os
import boto3
from botocore.exceptions import ClientError

_secrets_cache: dict = {}

def get_secret(secret_name: str, region: str = "us-east-1") -> dict | str:
    """Fetch a secret from AWS Secrets Manager with in-memory caching."""
    if secret_name in _secrets_cache:
        return _secrets_cache[secret_name]

    client = boto3.client("secretsmanager", region_name=region)
    try:
        response = client.get_secret_value(SecretId=secret_name)
        secret = response["SecretString"]
        # Try parsing as JSON, fall back to raw string
        try:
            parsed = json.loads(secret)
            _secrets_cache[secret_name] = parsed
            return parsed
        except json.JSONDecodeError:
            _secrets_cache[secret_name] = secret
            return secret
    except ClientError as e:
        raise RuntimeError(f"Failed to fetch secret '{secret_name}': {e}")


def get_database_url(db_name: str) -> str:
    """Build async PostgreSQL connection URL from Secrets Manager credentials."""
    # Allow override via env var for local development
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    from urllib.parse import quote_plus
    creds = get_secret("medilink/production/db-credentials")
    password = quote_plus(creds['password'])
    return (
        f"postgresql+asyncpg://{creds['username']}:{password}"
        f"@{creds['host']}:{creds['port']}/{db_name}"
    )


def get_rsa_private_key() -> str:
    """Fetch RSA private key for JWT signing (user-service only)."""
    env_key = os.getenv("JWT_PRIVATE_KEY")
    if env_key:
        return env_key.replace("\\n", "\n")
    return get_secret("medilink/production/jwt-rsa-private-key")


def get_rsa_public_key() -> str:
    """Fetch RSA public key for JWT verification (all services)."""
    env_key = os.getenv("JWT_PUBLIC_KEY")
    if env_key:
        return env_key.replace("\\n", "\n")
    return get_secret("medilink/production/jwt-rsa-public-key")
