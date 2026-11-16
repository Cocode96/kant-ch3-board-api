from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class ErrorDetail(BaseModel):
    location: list[str | int]
    code: str
    message: str

class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)

class ErrorResponse(BaseModel):
    error: ErrorBody

class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"

class Signup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=8, max_length=128)
    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PostInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)

class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    content: str
    author_id: int
    created_at: datetime

