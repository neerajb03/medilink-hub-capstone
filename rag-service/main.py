"""
rag-service: API-only RAG query endpoint.

Flow: query → Titan embedding → pgvector search → context assembly
      → Nova Lite v1 inference → Bedrock Guardrails → response with citations.

This service has NO workers and NO SQS consumer — that is rag-worker's job.
"""
import os
import json
from contextlib import asynccontextmanager
from uuid import UUID

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from logging_config import setup_logger
from auth.jwt import get_current_user
from aws_utils import get_database_url

logger = setup_logger("rag-service")

AWS_REGION            = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
LLM_MODEL_ID          = os.getenv("BEDROCK_LLM_MODEL_ID", "amazon.nova-lite-v1:0")
EMBED_MODEL_ID        = os.getenv("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
GUARDRAIL_ID          = os.getenv("BEDROCK_GUARDRAIL_ID", "")
GUARDRAIL_VERSION     = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
TOP_K                 = int(os.getenv("TOP_K_CHUNKS", "5"))

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)


# ── pgvector sync connection ──────────────────────────────────────────────────
def get_pg_conn():
    url = get_database_url("rag_db").replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(url)


# ── Titan embedding ───────────────────────────────────────────────────────────
def embed_query(text: str) -> list[float]:
    body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(resp["body"].read())["embedding"]


# ── pgvector similarity search ────────────────────────────────────────────────
def search_chunks(patient_id: str, query_vector: list[float], top_k: int) -> list[dict]:
    conn = get_pg_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"
            cur.execute(
                """
                SELECT document_id, chunk_index, content,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM document_chunks
                WHERE patient_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vector_str, patient_id, vector_str, top_k),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


# ── Nova Lite inference with Guardrails ───────────────────────────────────────
def invoke_nova(query: str, context_chunks: list[dict]) -> str:
    context = "\n\n".join(
        f"[Document {i+1}, chunk {c['chunk_index']}]:\n{c['content']}"
        for i, c in enumerate(context_chunks)
    )

    system_prompt = (
        "You are a medical assistant helping patients understand their own health records. "
        "Answer ONLY using the provided context. "
        "If the answer is not in the context, say 'I don't have enough information in your records to answer that.' "
        "Never fabricate medical information."
    )

    messages = [
        {
            "role": "user",
            "content": [{"text": f"Context from patient records:\n{context}\n\nQuestion: {query}"}],
        }
    ]

    body = json.dumps({
        "schemaVersion": "messages-v1",
        "system": [{"text": system_prompt}],
        "messages": messages,
        "inferenceConfig": {
            "maxTokens": 1024,
            "temperature": 0.1,   # low temperature = less hallucination
            "topP": 0.9,
        },
    })

    invoke_kwargs = dict(
        modelId=LLM_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    # Apply Bedrock Guardrails if configured (Layer 8 of anti-hallucination)
    if GUARDRAIL_ID:
        invoke_kwargs["guardrailIdentifier"] = GUARDRAIL_ID
        invoke_kwargs["guardrailVersion"] = GUARDRAIL_VERSION

    resp = bedrock.invoke_model(**invoke_kwargs)
    result = json.loads(resp["body"].read())
    return result["output"]["message"]["content"][0]["text"]


# ── FastAPI app ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan, title="MediLink RAG Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid input", "details": str(exc.errors())})


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/health")
async def health():
    return {"status": "ok"}


class RAGQueryRequest(BaseModel):
    query: str
    patient_id: str | None = None   # doctors can query on behalf of a patient


@app.post("/rag/query")
async def rag_query(data: RAGQueryRequest, user=Depends(get_current_user)):
    # Patients query their own records; doctors must supply patient_id
    if user["role"] == "patient":
        target_patient_id = user["user_id"]
    elif user["role"] == "doctor":
        if not data.patient_id:
            raise HTTPException(status_code=400, detail="patient_id is required for doctors")
        target_patient_id = data.patient_id
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    if not data.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        query_vector = embed_query(data.query)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=503, detail="Embedding service unavailable")

    chunks = search_chunks(target_patient_id, query_vector, TOP_K)

    if not chunks:
        return {
            "answer": "No relevant documents found in your medical records for this query.",
            "citations": [],
            "chunks_used": 0,
        }

    try:
        answer = invoke_nova(data.query, chunks)
    except Exception as e:
        logger.error(f"Bedrock inference failed: {e}")
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable")

    citations = [
        {"document_id": str(c["document_id"]), "chunk_index": c["chunk_index"], "similarity": round(float(c["similarity"]), 4)}
        for c in chunks
    ]

    logger.info(f"RAG query answered using {len(chunks)} chunks for patient {target_patient_id}")

    return {
        "answer": answer,
        "citations": citations,
        "chunks_used": len(chunks),
    }
