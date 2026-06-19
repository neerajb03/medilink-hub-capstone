import os
import io
from uuid import uuid4
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, File, UploadFile
from logging_config import setup_logger

logger = setup_logger("document-service")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator
from sqlalchemy import Column, Text, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.future import select
import boto3
from botocore.client import Config

from auth.jwt import get_current_user

# --- Database ---
from aws_utils import get_database_url
engine = create_async_engine(get_database_url("document_db"))
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    record_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    file_name = Column(Text, nullable=False)
    s3_key = Column(Text, nullable=False)
    uploaded_by = Column(Text, nullable=False)
    file_type = Column(Text, nullable=False)
    category = Column(Text, nullable=False, default="other")
    status = Column(Text, default="PENDING")
    
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_user_id = Column(PG_UUID(as_uuid=True), nullable=False)
    created_by_role = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False, index=True)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# --- S3 Client ---
s3_endpoint = os.getenv("S3_ENDPOINT", "http://minio:9000")
s3_access_key = os.getenv("S3_ACCESS_KEY", "minio")
s3_secret_key = os.getenv("S3_SECRET_KEY", "minio123")
s3_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# If S3_ENDPOINT is set to standard AWS or empty, use native AWS S3.
# This makes the exact same code work locally on MinIO and in production on AWS S3!
if not s3_endpoint or "amazonaws.com" in s3_endpoint:
    s3_client = boto3.client(
        "s3",
        region_name=s3_region,
        config=Config(signature_version="s3v4")
    )
else:
    s3_client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=s3_access_key,
        aws_secret_access_key=s3_secret_key,
        region_name=s3_region,
        config=Config(signature_version="s3v4")
    )


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Bucket
    bucket = os.getenv("S3_BUCKET_NAME", "medilink-docs")
    try:
        s3_client.head_bucket(Bucket=bucket)
    except Exception:
        try:
            if s3_region == "us-east-1":
                s3_client.create_bucket(Bucket=bucket)
            else:
                s3_client.create_bucket(
                    Bucket=bucket,
                    CreateBucketConfiguration={"LocationConstraint": s3_region}
                )
        except Exception as e:
            print(f"Error creating bucket or bucket already exists: {e}")
    yield


# --- App ---
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from logging_config import request_id_var
from uuid import uuid4, UUID

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid4())
        request_id_var.set(req_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

app.add_middleware(RequestIDMiddleware)


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
                "details": str(exc),
            }
        },
    )


VALID_CATEGORIES = [
    "lab_report",
    "prescription",
    "imaging",
    "discharge_summary",
    "insurance",
    "referral",
    "consultation",
    "other",
]


class PresignedUrlRequest(BaseModel):
    file_name: str
    file_type: str
    category: str = "other"
    appointment_id: str | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        if v not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}")
        return v

# --- Routes ---
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/documents/presigned-url", status_code=201)
async def get_presigned_url(
    data: PresignedUrlRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate file type
    allowed = ["application/pdf", "image/jpeg", "image/png"]
    if data.file_type not in allowed:
        raise HTTPException(status_code=400, detail="Only PDF, JPG, PNG allowed")

    doc_id = uuid4()
    patient_id = user["user_id"] # By default, assuming patient uploads for themselves
    
    if user["role"] == "doctor":
        if not data.appointment_id:
            raise HTTPException(status_code=400, detail="appointment_id is required for doctors to upload documents")
            
        # Verify appointment belongs to doctor
        import httpx
        INTERNAL_ALB_DNS = os.getenv("INTERNAL_ALB_DNS", "http://appointment-service:8002")
        if not INTERNAL_ALB_DNS.startswith("http"):
            INTERNAL_ALB_DNS = "http://" + INTERNAL_ALB_DNS
            
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{INTERNAL_ALB_DNS}/appointments/{data.appointment_id}", timeout=10.0, headers={"Authorization": f"Bearer {user['token']}"})
                if resp.status_code == 200:
                    appt = resp.json()
                    if appt.get("status") != "completed":
                        raise HTTPException(status_code=400, detail="Document can only be uploaded for a completed appointment")
                    if appt.get("doctor_id") != user["user_id"]:
                        raise HTTPException(status_code=403, detail="You can only upload documents for your own appointments")
                    patient_id = appt.get("patient_id")
                else:
                    raise HTTPException(status_code=400, detail="Failed to validate appointment or appointment not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to communicate with appointment service: {e}")
            raise HTTPException(status_code=503, detail="Appointment service unavailable")

    ext = data.file_name.split(".")[-1] if "." in data.file_name else "bin"
    rec_part = data.appointment_id if data.appointment_id else "no-record"
    object_name = f"{patient_id}/{rec_part}/{doc_id}.{ext}"
    bucket = os.getenv("S3_BUCKET_NAME", "medilink-docs")

    url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": object_name,
            "ContentType": data.file_type
        },
        ExpiresIn=3600
    )

    doc = Document(
        id=doc_id,
        patient_id=UUID(patient_id),
        record_id=UUID(data.appointment_id) if data.appointment_id else None,
        file_name=data.file_name,
        s3_key=object_name,
        uploaded_by=user["role"],
        file_type=data.file_type,
        category=data.category,
        status="PENDING",
        created_by_user_id=UUID(user["user_id"]),
        created_by_role=user["role"]
    )
    db.add(doc)
    await db.commit()

    return {"upload_url": url, "document_id": str(doc_id), "s3_key": object_name}


@app.post("/documents/{doc_id}/confirm")
async def confirm_upload(
    doc_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if str(doc.created_by_user_id) != user["user_id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    doc.status = "COMPLETED"
    await db.commit()
    return {"status": "success", "document_id": str(doc.id)}


@app.get("/documents")
async def list_documents(
    appointment_id: str | None = None,
    patient_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user["role"] not in ("patient", "doctor", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    import httpx
    INTERNAL_ALB_DNS = os.getenv("INTERNAL_ALB_DNS", "http://appointment-service:8002")
    if not INTERNAL_ALB_DNS.startswith("http"):
        INTERNAL_ALB_DNS = "http://" + INTERNAL_ALB_DNS

    query = select(Document).where(Document.is_deleted == False).limit(limit).offset(offset)

    if user["role"] == "patient":
        query = query.where(Document.patient_id == UUID(user["user_id"]))

    elif user["role"] == "doctor":
        if appointment_id:
            # Filter by specific appointment — verify doctor owns it
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{INTERNAL_ALB_DNS}/appointments/{appointment_id}",
                        timeout=10.0,
                        headers={"Authorization": f"Bearer {user['token']}"},
                    )
                    if resp.status_code != 200:
                        raise HTTPException(status_code=400, detail="Appointment not found")
                    appt = resp.json()
                    if appt.get("doctor_id") != user["user_id"]:
                        raise HTTPException(status_code=403, detail="Access denied")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Appointment service unavailable: {e}")
                raise HTTPException(status_code=503, detail="Appointment service unavailable")
            query = query.where(Document.record_id == UUID(appointment_id))

        elif patient_id:
            # Full patient history — verify doctor-patient relationship first
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{INTERNAL_ALB_DNS}/appointments/check-relationship",
                        params={"doctor_id": user["user_id"], "patient_id": patient_id},
                        timeout=10.0,
                        headers={"Authorization": f"Bearer {user['token']}"},
                    )
                    if resp.status_code != 200 or not resp.json().get("has_relationship"):
                        raise HTTPException(status_code=403, detail="No doctor-patient relationship found")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Appointment service unavailable: {e}")
                raise HTTPException(status_code=503, detail="Unable to verify access permissions")
            query = query.where(Document.patient_id == UUID(patient_id))

        else:
            # No filter — return only docs the doctor uploaded
            query = query.where(Document.created_by_user_id == UUID(user["user_id"]))

    result = await db.execute(query)
    documents = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "patient_id": str(d.patient_id),
            "record_id": str(d.record_id) if d.record_id else None,
            "file_name": d.file_name,
            "s3_key": d.s3_key,
            "uploaded_by": d.uploaded_by,
            "file_type": d.file_type,
            "category": d.category,
            "status": d.status,
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
    result = await db.execute(select(Document).where(Document.id == doc_id).where(Document.is_deleted == False))
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if user["role"] == "patient" and str(doc.patient_id) != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    if user["role"] == "doctor":
        import httpx
        INTERNAL_ALB_DNS = os.getenv("INTERNAL_ALB_DNS", "http://appointment-service:8002")
        if not INTERNAL_ALB_DNS.startswith("http"):
            INTERNAL_ALB_DNS = "http://" + INTERNAL_ALB_DNS
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{INTERNAL_ALB_DNS}/appointments/check-relationship",
                    params={"doctor_id": user["user_id"], "patient_id": str(doc.patient_id)},
                    timeout=10.0,
                    headers={"Authorization": f"Bearer {user['token']}"},
                )
                if resp.status_code != 200 or not resp.json().get("has_relationship"):
                    raise HTTPException(status_code=403, detail="Access denied — no doctor-patient relationship")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to verify doctor-patient relationship: {e}")
            raise HTTPException(status_code=503, detail="Unable to verify access permissions")

    # Generate presigned URL
    bucket = os.getenv("S3_BUCKET_NAME", "medilink-docs")
    from datetime import timedelta

    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": doc.s3_key},
        ExpiresIn=300 # 5 minutes expiry for security
    )
    # Replace internal minio host with localhost for browser access only if running locally
    if "minio:9000" in url:
        url = url.replace("minio:9000", "localhost:9000")

    return {
        "id": str(doc.id),
        "file_name": doc.file_name,
        "url": url,
    }
