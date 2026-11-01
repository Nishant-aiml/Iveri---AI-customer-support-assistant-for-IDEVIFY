import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.models.business import Business
from app.models.user import User
from app.schemas.auth import UserRegisterRequest, UserLoginRequest, TokenResponse, UserProfileResponse
from app.utils.security import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

def generate_slug(name: str) -> str:
    """Generates a clean URL slug from business name."""
    clean = re.sub(r"[^\w\s-]", "", name).strip().lower()
    slug = re.sub(r"[-\s]+", "-", clean)
    if not slug:
        slug = "business"
    # Append short random hex to guarantee uniqueness
    return f"{slug}-{uuid.uuid4().hex[:6]}"

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(req: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Registers a new business owner or customer account."""
    # Check if email already registered
    existing_user_query = select(User).where(User.email == req.email)
    existing_user = (await db.execute(existing_user_query)).scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists."
        )

    # Create new business workspace for the owner
    slug = generate_slug(req.business_name)
    business = Business(
        name=req.business_name,
        slug=slug,
        share_token=str(uuid.uuid4())
    )
    db.add(business)
    await db.flush()  # Populates business.id

    # Create user associated with the business
    user = User(
        business_id=business.id,
        email=req.email,
        password_hash=hash_password(req.password),
        role=req.role
    )
    db.add(user)
    await db.commit()
    await db.refresh(business)
    await db.refresh(user)

    # Issue access token
    token_payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "business_id": business.id
    }
    access_token = create_access_token(token_payload)

    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        business_id=business.id,
        role=user.role,
        business_name=business.name,
        business_slug=business.slug,
        share_token=business.share_token
    )

@router.post("/login", response_model=TokenResponse)
async def login_user(req: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticates user and returns JWT token."""
    user_query = select(User).where(User.email == req.email)
    user = (await db.execute(user_query)).scalar_one_or_none()
    
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password credentials."
        )

    # Retrieve business details
    biz_query = select(Business).where(Business.id == user.business_id)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business workspace associated with this user was not found."
        )

    token_payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "business_id": business.id
    }
    access_token = create_access_token(token_payload)

    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        business_id=business.id,
        role=user.role,
        business_name=business.name,
        business_slug=business.slug,
        share_token=business.share_token
    )

@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Returns profile information for the authenticated user and their business."""
    biz_query = select(Business).where(Business.id == current_user.business_id)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        business_id=business.id,
        business_name=business.name,
        business_slug=business.slug,
        share_token=business.share_token,
        starter_questions=business.starter_questions,
        brand_color=business.brand_color,
        tone=business.tone
    )
