import re
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List

class UserRegisterRequest(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field(default="owner")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and one number.")
        return v

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

class FirebaseLoginRequest(BaseModel):
    id_token: str = Field(..., description="Firebase Auth ID Token")
    business_name: Optional[str] = Field(None, max_length=100)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    business_id: str
    role: str
    business_name: str
    business_slug: str
    share_token: str

class UserProfileResponse(BaseModel):
    id: str
    email: str
    role: str
    business_id: str
    business_name: str
    business_slug: str
    share_token: str
    starter_questions: List[str]
    brand_color: str
    tone: str
