from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List

class UserRegisterRequest(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: str = Field(default="owner")

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

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
