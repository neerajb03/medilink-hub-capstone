import os
from uuid import uuid4, UUID
from datetime import datetime
from contextlib import asynccontextmanager

import time
from fastapi import FastAPI, HTTPException, Depends, Request
from logging_config import setup_logger

logger = setup_logger("health-service")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator
from sqlalchemy import Column, Text, DateTime, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.future import select

from auth.jwt import get_current_user

# --- Database ---
from aws_utils import get_database_url
engine = create_async_engine(get_database_url("health_db"))
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = "health_records"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    doctor_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    appointment_id = Column(PG_UUID(as_uuid=True), nullable=True)
    title = Column(Text, nullable=True)
    description = Column(Text, nullable=False)
    diagnosis = Column(Text, nullable=True)
    prescription_text = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_user_id = Column(PG_UUID(as_uuid=True), nullable=False)
    created_by_role = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False, index=True)
    
    __table_args__ = (
        Index('uniq_health_record_per_appointment', 'appointment_id', unique=True, postgresql_where=(appointment_id.isnot(None))),
    )


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
from uuid import uuid4

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
                "details": "",
            }
        },
    )


# --- Schemas ---
class RecordCreate(BaseModel):
    patient_id: str
    appointment_id: str | None = None
    title: str | None = None
    description: str
    diagnosis: str | None = None
    prescription_text: str | None = None

    @field_validator("description")
    @classmethod
    def description_valid(cls, v):
        if not v or not v.strip():
            raise ValueError("Description is required")
        if len(v) > 1000:
            raise ValueError("Description must be at most 1000 characters")
        return v.strip()


import httpx

# --- Routes ---
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/health-records", status_code=201)
async def create_record(
    data: RecordCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can create health records")

    try:
        patient_uuid = UUID(data.patient_id)
        doctor_uuid = UUID(user["user_id"])
        appointment_uuid = UUID(data.appointment_id) if data.appointment_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format for patient or appointment ID. Please select a valid patient.")

    if appointment_uuid:
        INTERNAL_ALB_DNS = os.getenv("INTERNAL_ALB_DNS", "http://internal-alb")
        if not INTERNAL_ALB_DNS.startswith("http"):
            INTERNAL_ALB_DNS = "http://" + INTERNAL_ALB_DNS
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{INTERNAL_ALB_DNS}/appointments/{str(appointment_uuid)}", headers={"Authorization": f"Bearer {user['token']}"})
                if resp.status_code == 200:
                    appt = resp.json()
                    if appt.get("status") != "completed":
                        raise HTTPException(status_code=400, detail="Health record can only be created for a completed appointment")
                    if appt.get("doctor_id") != user["user_id"]:
                        raise HTTPException(status_code=403, detail="You can only create health records for your own appointments")
                else:
                    # Strict enforcement as per user rules
                    raise HTTPException(status_code=400, detail="Failed to validate appointment or appointment not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to communicate with appointment service: {e}")
            raise HTTPException(status_code=503, detail="Appointment service unavailable")

    record = Record(
        patient_id=patient_uuid,
        doctor_id=doctor_uuid,
        appointment_id=appointment_uuid,
        title=data.title,
        description=data.description,
        diagnosis=data.diagnosis,
        prescription_text=data.prescription_text,
        created_by_user_id=doctor_uuid,
        created_by_role=user["role"]
    )
    db.add(record)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        if "uniq_health_record_per_appointment" in str(e):
            raise HTTPException(status_code=400, detail="A health record has already been created for this appointment.")
        raise HTTPException(status_code=400, detail="Database error while saving health record.")
    await db.refresh(record)

    return {
        "id": str(record.id),
        "patient_id": str(record.patient_id),
        "doctor_id": str(record.doctor_id),
        "appointment_id": str(record.appointment_id) if record.appointment_id else None,
        "title": record.title,
        "description": record.description,
        "created_at": record.created_at.isoformat(),
    }


@app.get("/health-records")
async def list_records(
    patient_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user["role"] not in ("patient", "doctor", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    query = select(Record).where(Record.is_deleted == False).limit(limit).offset(offset)

    if user["role"] == "patient":
        query = query.where(Record.patient_id == user["user_id"])
    elif user["role"] == "doctor":
        if not patient_id:
            query = query.where(Record.doctor_id == user["user_id"])
        else:
            query = query.where(Record.doctor_id == user["user_id"]).where(Record.patient_id == patient_id)

    result = await db.execute(query)
    records = result.scalars().all()
    
    return [
        {
            "id": str(r.id),
            "patient_id": str(r.patient_id),
            "doctor_id": str(r.doctor_id),
            "appointment_id": str(r.appointment_id) if r.appointment_id else None,
            "title": r.title,
            "description": r.description,
            "diagnosis": r.diagnosis,
            "prescription_text": r.prescription_text,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in records
    ]

class ChatRequest(BaseModel):
    message: str
    appointment_id: str | None = None

import httpx
from aws_utils import get_secret

hf_down_until = 0

async def call_huggingface(message: str, timeout: float = 10.0) -> str:
    hf_token = get_secret("medilink/production/hf-api-key")
    if not hf_token or hf_token == "REPLACE_ME_MANUALLY_IN_CONSOLE":
        raise Exception("AI service not configured")

    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {
        "inputs": f"Patient symptoms: {message}. What could this be? Keep it brief and suggest consulting a doctor.",
        "parameters": {"max_new_tokens": 100}
    }
    
    API_URL = "https://api-inference.huggingface.co/models/HuggingFaceH4/zephyr-7b-beta"
    async with httpx.AsyncClient() as client:
        resp = await client.post(API_URL, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()
        return result[0].get("generated_text", "Sorry, I could not process your symptoms.").replace(payload["inputs"], "").strip()

async def call_groq(message: str, timeout: float = 5.0) -> str:
    groq_token = get_secret("medilink/production/groq-api-key")
    if not groq_token or groq_token == "REPLACE_ME_MANUALLY_IN_CONSOLE":
        raise Exception("Groq not configured")

    headers = {
        "Authorization": f"Bearer {groq_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": f"Patient symptoms: {message}. What could this be? Keep it brief and suggest consulting a doctor."}],
        "max_tokens": 100
    }
    API_URL = "https://api.groq.com/openai/v1/chat/completions"
    async with httpx.AsyncClient() as client:
        resp = await client.post(API_URL, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"].strip()

async def use_groq_or_fallback(message: str):
    try:
        response = await call_groq(message, timeout=5.0)
        logger.info("Groq success")
        return {
            "reply": response,
            "source": "groq",
            "is_fallback": True
        }
    except Exception as e:
        logger.warning("Groq also failed", extra={"error": str(e)})
        
        # Conversational rule-based fallback
        msg_lower = message.lower()
        if "fever" in msg_lower:
            reply = "You may have a fever. Stay hydrated and monitor your temperature. Can you describe any other symptoms?"
        elif "pain" in msg_lower:
            reply = "Can you describe where the pain is located and how severe it is?"
        else:
            reply = "I'm having trouble accessing my AI services right now, but I'm here to help with general health questions. Could you provide more details about how you're feeling?"

        return {
            "reply": reply,
            "source": "system",
            "is_fallback": True
        }

@app.post("/chat")
async def chat_endpoint(data: ChatRequest, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    global hf_down_until

    if user["role"] not in ["patient", "doctor"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    context_msg = data.message
    if data.appointment_id:
        # Fetch appointment details
        INTERNAL_ALB_DNS = os.getenv("INTERNAL_ALB_DNS", "http://internal-alb")
        if not INTERNAL_ALB_DNS.startswith("http"):
            INTERNAL_ALB_DNS = "http://" + INTERNAL_ALB_DNS
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{INTERNAL_ALB_DNS}/appointments/{data.appointment_id}")
                if resp.status_code == 200:
                    appt = resp.json()
                    # Ensure doctor owns the appointment (or patient)
                    if user["role"] == "admin" or appt.get("doctor_id") == user["user_id"] or appt.get("patient_id") == user["user_id"]:
                        patient_id = appt.get("patient_id")
                        
                        # Fetch patient history from DB
                        from sqlalchemy import select
                        records = await db.execute(select(HealthRecord).where(HealthRecord.patient_id == patient_id))
                        history = records.scalars().all()
                        
                        context_prefix = "Patient Medical Context:\n"
                        if history:
                            for idx, r in enumerate(history[-5:]): # Last 5 records
                                context_prefix += f"- Record {idx+1}: {r.diagnosis or 'No diagnosis'}. {r.description}\n"
                        else:
                            context_prefix += "No prior medical records found.\n"
                        
                        context_msg = f"{context_prefix}\nDoctor Query: {data.message}"
        except Exception as e:
            logger.error(f"Chat context fetch failed: {e}")
            # Non-fatal, just continue with original message

    # Skip HF if it's marked down
    if time.time() < hf_down_until:
        return await use_groq_or_fallback(context_msg)

    try:
        response = await call_huggingface(context_msg, timeout=10.0)
        logger.info("HF success")
        return {
            "reply": response,
            "source": "hf",
            "is_fallback": False
        }
    except Exception as e:
        # Circuit breaker trigger
        hf_down_until = time.time() + 60
        logger.warning("HF timeout/failure", extra={"error": str(e)})
        return await use_groq_or_fallback(context_msg)
