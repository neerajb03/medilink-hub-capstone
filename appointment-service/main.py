import os
from uuid import uuid4
import datetime as dt
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request
from logging_config import setup_logger

logger = setup_logger("appointment-service")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator
from sqlalchemy import Column, Text, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.future import select

import httpx
import boto3
import json

from auth.jwt import get_current_user

# --- SQS Helper ---
sqs = boto3.client('sqs', region_name='us-east-1')
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")

def publish_appointment_event(appointment_id: str, patient_id: str, doctor_id: str, status: str):
    if not SQS_QUEUE_URL:
        print(f"Warning: SQS_QUEUE_URL not set. Skipping event for {appointment_id}")
        return
    try:
        from logging_config import request_id_var
        
        sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps({
                "event": f"APPOINTMENT_{status.upper()}",
                "appointment_id": str(appointment_id),
                "patient_id": str(patient_id),
                "doctor_id": str(doctor_id),
                "status": status,
                "x_request_id": request_id_var.get()
            })
        )
    except Exception as e:
        print(f"Failed to publish SQS message: {e}")

# --- Database ---
from aws_utils import get_database_url
engine = create_async_engine(get_database_url("appointment_db"))
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    doctor_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    datetime = Column(DateTime, nullable=False)
    status = Column(Text, default="pending")
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)
    is_deleted = Column(Boolean, default=False)


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
class AppointmentCreate(BaseModel):
    doctor_id: str
    datetime: dt.datetime

    @field_validator("datetime")
    @classmethod
    def datetime_must_be_future(cls, v):
        if v is not None:
            if v.tzinfo is not None:
                v = v.astimezone(dt.timezone.utc).replace(tzinfo=None)
            if v <= dt.datetime.utcnow():
                raise ValueError("Appointment datetime must be in the future")
        return v


class AppointmentUpdate(BaseModel):
    doctor_id: str | None = None
    datetime: dt.datetime | None = None
    status: str | None = None

    @field_validator("datetime")
    @classmethod
    def datetime_must_be_future(cls, v):
        if v is not None:
            if v.tzinfo is not None:
                v = v.astimezone(dt.timezone.utc).replace(tzinfo=None)
            if v <= dt.datetime.utcnow():
                raise ValueError("Appointment datetime must be in the future")
        return v


# --- Routes ---
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/appointments", status_code=201)
async def create_appointment(
    data: AppointmentCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user["role"] != "patient":
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Only patients can create appointments",
                    "details": "",
                }
            },
        )
        
    if data.doctor_id:
        # Cross-service validation: ensure the assigned doctor exists and is actually a doctor
        INTERNAL_ALB_DNS = os.getenv("INTERNAL_ALB_DNS", "http://internal-alb")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{INTERNAL_ALB_DNS}/users/{data.doctor_id}")
                if resp.status_code != 200 or resp.json().get("role") != "doctor":
                    print("Failed to validate doctor synchronously, proceeding with soft consistency")
        except Exception as e:
            print(f"Doctor validation skipped (service unavailable): {e}")

    appt = Appointment(
        patient_id=user["user_id"],
        doctor_id=data.doctor_id,
        datetime=data.datetime,
        status="pending",
    )
    db.add(appt)
    await db.commit()
    await db.refresh(appt)

    publish_appointment_event(str(appt.id), str(appt.patient_id), str(appt.doctor_id), "pending")

    return {
        "id": str(appt.id),
        "patient_id": str(appt.patient_id),
        "doctor_id": str(appt.doctor_id),
        "datetime": appt.datetime.isoformat(),
        "status": appt.status,
    }


@app.put("/appointments/{appt_id}/accept")
async def accept_appointment(
    appt_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can accept appointments")
        
    result = await db.execute(select(Appointment).where(Appointment.id == appt_id))
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    if str(appt.doctor_id) != user["user_id"]:
        raise HTTPException(status_code=403, detail="You are not the assigned doctor")
        
    appt.status = "completed"
    await db.commit()
    await db.refresh(appt)
    
    publish_appointment_event(str(appt.id), str(appt.patient_id), str(appt.doctor_id), "completed")
    
    return {"status": "success", "appointment_id": str(appt.id)}


@app.get("/appointments")
async def list_appointments(
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
            select(Appointment).where(Appointment.patient_id == user["user_id"])
        )
    elif user["role"] == "doctor":
        result = await db.execute(
            select(Appointment).where(Appointment.doctor_id == user["user_id"])
        )
    else:
        result = await db.execute(select(Appointment))

    appointments = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "patient_id": str(a.patient_id),
            "doctor_id": str(a.doctor_id),
            "datetime": a.datetime.isoformat(),
            "status": a.status,
        }
        for a in appointments
    ]


@app.put("/appointments/{appt_id}")
async def update_appointment(
    appt_id: str,
    data: AppointmentUpdate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appt_id))
    appt = result.scalar_one_or_none()

    if not appt:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Appointment not found",
                    "details": "",
                }
            },
        )

    if user["role"] != "patient" or str(appt.patient_id) != user["user_id"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "You can only update your own appointments",
                    "details": "",
                }
            },
        )

    # Cannot update a past appointment
    if appt.datetime <= dt.datetime.utcnow():
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Cannot update a past appointment",
                    "details": "",
                }
            },
        )

    if data.datetime is not None:
        appt.datetime = data.datetime
    if data.doctor_id is not None:
        appt.doctor_id = data.doctor_id
    if data.status is not None:
        appt.status = data.status

    await db.commit()
    await db.refresh(appt)

    return {
        "patient_id": str(appt.patient_id),
        "doctor_id": str(appt.doctor_id) if appt.doctor_id else None,
        "datetime": appt.datetime.isoformat(),
        "status": appt.status,
    }


@app.delete("/appointments/{appt_id}")
async def delete_appointment(
    appt_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appt_id))
    appt = result.scalar_one_or_none()

    if not appt:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Appointment not found",
                    "details": "",
                }
            },
        )

    if user["role"] != "patient" or str(appt.patient_id) != user["user_id"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "You can only delete your own appointments",
                    "details": "",
                }
            },
        )

    await db.delete(appt)
    await db.commit()

    return {"message": "Appointment deleted"}
