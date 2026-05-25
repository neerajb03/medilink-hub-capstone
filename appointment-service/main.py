import os
from uuid import uuid4
import datetime as dt
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator
from sqlalchemy import Column, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.future import select

from auth.jwt import get_current_user

# --- Database ---
engine = create_async_engine(os.getenv("DATABASE_URL"))
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), nullable=True)
    datetime = Column(DateTime, nullable=False)
    status = Column(Text, default="pending")
    created_at = Column(DateTime, default=dt.datetime.utcnow)


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


# --- Schemas ---
class AppointmentCreate(BaseModel):
    doctor_id: str | None = None
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

    appt = Appointment(
        user_id=user["user_id"],
        doctor_id=data.doctor_id,
        datetime=data.datetime,
        status="pending",
    )
    db.add(appt)
    await db.commit()
    await db.refresh(appt)

    return {
        "id": str(appt.id),
        "user_id": str(appt.user_id),
        "doctor_id": str(appt.doctor_id) if appt.doctor_id else None,
        "datetime": appt.datetime.isoformat(),
        "status": appt.status,
    }


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
            select(Appointment).where(Appointment.user_id == user["user_id"])
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
            "user_id": str(a.user_id),
            "doctor_id": str(a.doctor_id) if a.doctor_id else None,
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

    if user["role"] != "patient" or str(appt.user_id) != user["user_id"]:
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
        "id": str(appt.id),
        "user_id": str(appt.user_id),
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

    if user["role"] != "patient" or str(appt.user_id) != user["user_id"]:
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
