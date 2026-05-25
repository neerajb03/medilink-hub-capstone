import os
import io
from uuid import uuid4
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Column, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.future import select
from minio import Minio

from auth.jwt import get_current_user

# --- Database ---
engine = create_async_engine(os.getenv("DATABASE_URL"))
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    file_name = Column(Text, nullable=False)
    s3_key = Column(Text, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# --- MinIO Client ---
minio_client = Minio(
    os.getenv("S3_ENDPOINT", "http://minio:9000").replace("http://", ""),
    access_key=os.getenv("S3_ACCESS_KEY", "minio"),
    secret_key=os.getenv("S3_SECRET_KEY", "minio123"),
    secure=False,
)


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Bucket
    bucket = os.getenv("S3_BUCKET_NAME", "medilink-docs")
    if not minio_client.bucket_exists(bucket):
        minio_client.make_bucket(bucket)
    yield


# --- App ---
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Error Handlers ---
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid input",
                "details": str(exc.errors()),
            }
        },
    )


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Server error",
                "details": "",
            }
        },
    )


# --- Routes ---
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user["role"] != "patient":
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Only patients can upload documents",
                    "details": "",
                }
            },
        )

    # Validate file type
    allowed = ["application/pdf", "image/jpeg", "image/png"]
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_FILE_TYPE",
                    "message": "Only PDF, JPG, PNG allowed",
                    "details": "",
                }
            },
        )

    # Validate size (stream first 5MB+1 byte to check)
    MAX = 5 * 1024 * 1024
    content = await file.read(MAX + 1)
    if len(content) > MAX:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "FILE_TOO_LARGE",
                    "message": "Max 5MB",
                    "details": "",
                }
            },
        )

    # Reset and stream to MinIO
    file_bytes = io.BytesIO(content)
    object_name = f"patients/{user['user_id']}/{file.filename}"
    bucket = os.getenv("S3_BUCKET_NAME", "medilink-docs")

    minio_client.put_object(
        bucket,
        object_name,
        file_bytes,
        length=len(content),
        content_type=file.content_type,
    )

    # Save metadata to DB
    doc = Document(
        user_id=user["user_id"],
        file_name=file.filename,
        s3_key=object_name,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return {"message": "Uploaded", "key": object_name, "id": str(doc.id)}


@app.get("/documents")
async def list_documents(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user["role"] not in ("patient", "doctor", "admin"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Access denied",
                    "details": "",
                }
            },
        )

    if user["role"] == "patient":
        result = await db.execute(
            select(Document).where(Document.user_id == user["user_id"])
        )
    else:
        result = await db.execute(select(Document))

    documents = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "user_id": str(d.user_id),
            "file_name": d.file_name,
            "s3_key": d.s3_key,
            "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in documents
    ]


@app.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Document not found",
                    "details": "",
                }
            },
        )

    if user["role"] == "patient" and str(doc.user_id) != user["user_id"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Access denied",
                    "details": "",
                }
            },
        )

    # Generate presigned URL
    bucket = os.getenv("S3_BUCKET_NAME", "medilink-docs")
    from datetime import timedelta

    url = minio_client.presigned_get_object(bucket, doc.s3_key, expires=timedelta(hours=1))
    # Replace internal minio host with localhost for browser access
    url = url.replace("minio:9000", "localhost:9000")

    return {
        "id": str(doc.id),
        "file_name": doc.file_name,
        "url": url,
    }
