"""
rag-worker: SQS consumer that OCRs documents with Textract, chunks text,
generates Titan embeddings, and stores vectors in pgvector (RDS).

Scaling: KEDA ScaledObject drives replica count based on SQS queue depth.
Each replica processes one message at a time (long-poll → process → delete).
"""
import os
import json
import time
import boto3
import psycopg2
from psycopg2.extras import execute_values
from logging_config import setup_logger
from aws_utils import get_database_url

logger = setup_logger("rag-worker")

AWS_REGION      = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
SQS_QUEUE_URL   = os.getenv("SQS_RAG_QUEUE_URL")          # set in Helm values
S3_BUCKET       = os.getenv("S3_BUCKET_NAME", "medilink-docs-production-bucket")
CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE", "500"))       # characters per chunk
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "50"))

sqs      = boto3.client("sqs",      region_name=AWS_REGION)
textract = boto3.client("textract", region_name=AWS_REGION)
bedrock  = boto3.client("bedrock-runtime", region_name=AWS_REGION)


# ── pgvector connection ────────────────────────────────────────────────────────
def get_pg_conn():
    url = get_database_url("rag_db")
    # asyncpg URL → sync psycopg2 URL for pgvector inserts
    sync_url = url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id          SERIAL PRIMARY KEY,
                document_id UUID        NOT NULL,
                patient_id  UUID        NOT NULL,
                chunk_index INT         NOT NULL,
                content     TEXT        NOT NULL,
                embedding   vector(1024),
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx
            ON document_chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
        """)
    conn.commit()
    return conn


# ── Textract OCR ──────────────────────────────────────────────────────────────
def extract_text(s3_key: str) -> str:
    """Synchronous Textract call — works for PDFs < 5 pages; async for larger."""
    try:
        response = textract.detect_document_text(
            Document={"S3Object": {"Bucket": S3_BUCKET, "Name": s3_key}}
        )
        blocks = response.get("Blocks", [])
        lines = [b["Text"] for b in blocks if b["BlockType"] == "LINE"]
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Textract failed for {s3_key}: {e}")
        raise


# ── Chunking ──────────────────────────────────────────────────────────────────
def chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c.strip() for c in chunks if c.strip()]


# ── Titan Text Embeddings v2 (1024 dims) ──────────────────────────────────────
def embed(text: str) -> list[float]:
    body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(response["body"].read())["embedding"]


# ── pgvector insert ───────────────────────────────────────────────────────────
def store_chunks(conn, document_id: str, patient_id: str, chunks: list[str]):
    rows = []
    for idx, chunk in enumerate(chunks):
        try:
            vector = embed(chunk)
            rows.append((document_id, patient_id, idx, chunk, vector))
        except Exception as e:
            logger.error(f"Embedding failed for chunk {idx}: {e}")

    if rows:
        with conn.cursor() as cur:
            # Delete old chunks for this document (idempotent re-processing)
            cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
            execute_values(
                cur,
                """INSERT INTO document_chunks
                   (document_id, patient_id, chunk_index, content, embedding)
                   VALUES %s""",
                rows,
            )
        conn.commit()
        logger.info(f"Stored {len(rows)} chunks for document {document_id}")


# ── SQS consumer loop ─────────────────────────────────────────────────────────
def process_message(conn, message: dict):
    body = json.loads(message["Body"])
    document_id = body["document_id"]
    patient_id  = body["patient_id"]
    s3_key      = body["s3_key"]

    logger.info(f"Processing document {document_id} from s3://{S3_BUCKET}/{s3_key}")

    text = extract_text(s3_key)
    if not text.strip():
        logger.warning(f"No text extracted from {s3_key} — skipping")
        return

    chunks = chunk_text(text)
    logger.info(f"Split into {len(chunks)} chunks")

    store_chunks(conn, document_id, patient_id, chunks)


def main():
    if not SQS_QUEUE_URL:
        raise RuntimeError("SQS_RAG_QUEUE_URL env var is not set")

    logger.info("rag-worker starting — connecting to database")
    conn = get_pg_conn()
    logger.info(f"Polling SQS queue: {SQS_QUEUE_URL}")

    while True:
        response = sqs.receive_message(
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,           # long-poll to reduce empty receives
            VisibilityTimeout=300,        # matches SQS queue setting
        )

        messages = response.get("Messages", [])
        if not messages:
            continue

        message = messages[0]
        receipt_handle = message["ReceiptHandle"]

        try:
            process_message(conn, message)
            # Only delete on SUCCESS — failures stay visible for retry → DLQ
            sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
            logger.info("Message processed and deleted")
        except Exception as e:
            logger.error(f"Message processing failed: {e} — leaving for retry/DLQ")


if __name__ == "__main__":
    main()
