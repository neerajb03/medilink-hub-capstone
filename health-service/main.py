import os
from uuid import uuid4
from datetime import datetime
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


class Record(Base):
    __tablename__ = "records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


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
class RecordCreate(BaseModel):
    user_id: str
    description: str

    @field_validator("description")
    @classmethod
    def description_valid(cls, v):
        if not v or not v.strip():
            raise ValueError("Description is required")
        if len(v) > 1000:
            raise ValueError("Description must be at most 1000 characters")
        return v.strip()


# --- Routes ---
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/records", status_code=201)
async def create_record(
    data: RecordCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user["role"] != "doctor":
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Only doctors can create records",
                    "details": "",
                }
            },
        )

    record = Record(
        user_id=data.user_id,
        description=data.description,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return {
        "id": str(record.id),
        "user_id": str(record.user_id),
        "description": record.description,
        "created_at": record.created_at.isoformat(),
    }


@app.get("/records")
async def list_records(
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
            select(Record).where(Record.user_id == user["user_id"])
        )
    else:
        result = await db.execute(select(Record))

    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "user_id": str(r.user_id),
            "description": r.description,
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]
