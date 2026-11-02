import logging
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db, get_database_health
from app.models.business import Business
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest, UserLoginRequest, FirebaseLoginRequest, TokenResponse, UserProfileResponse,
    AccountRenameRequest, ChangePasswordRequest, DeleteAccountRequest
)
from app.utils.security import hash_password, verify_password, create_access_token, get_current_user, get_current_owner
from app.services.firebase_auth import firebase_auth_service
from app.services.vector_store import vector_store_service
from app.services.bm25_store import bm25_store_service

logger = logging.getLogger(__name__)

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
    """Registers a new business owner or customer account with case-insensitive email normalization."""
    clean_email = req.email.strip().lower()

    # Check if email already registered (case-insensitive)
    from sqlalchemy import func
    existing_user_query = select(User).where(func.lower(User.email) == clean_email)
    existing_user = (await db.execute(existing_user_query)).scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists. Please sign in with your password."
        )

    # Create new business workspace for the owner
    slug = generate_slug(req.business_name)
    business = Business(
        name=req.business_name.strip(),
        slug=slug,
        share_token=str(uuid.uuid4())
    )
    db.add(business)
    await db.flush()  # Populates business.id

    # Create user associated with the business
    user = User(
        business_id=business.id,
        email=clean_email,
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
    """Authenticates user with case-insensitive email matching and returns JWT token."""
    clean_email = req.email.strip().lower()
    from sqlalchemy import func
    user_query = select(User).where(func.lower(User.email) == clean_email)
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

@router.get("/active-owner")
async def get_active_owner_workspace(db: AsyncSession = Depends(get_db)):
    """
    Seamless cross-device discovery helper:
    Returns the most recently active workspace name and owner email to simplify signing in on mobile/second devices without losing data.
    """
    res = await db.execute(
        select(User, Business)
        .join(Business, User.business_id == Business.id)
        .where(User.role == "owner")
        .order_by(User.created_at.desc())
        .limit(1)
    )
    row = res.first()
    if row:
        u, b = row
        return {
            "has_active_workspace": True,
            "business_name": b.name,
            "business_slug": b.slug,
            "owner_email": u.email
        }
    return {"has_active_workspace": False}

@router.get("/session/validate")
async def validate_session(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Validates session token freshness and multi-device connection status."""
    biz = (await db.execute(select(Business).where(Business.id == current_user.business_id))).scalar_one_or_none()
    return {
        "valid": True,
        "user_id": current_user.id,
        "email": current_user.email,
        "business_id": current_user.business_id,
        "business_name": biz.name if biz else "Business Workspace",
        "business_slug": biz.slug if biz else "",
        "share_token": biz.share_token if biz else ""
    }

@router.post("/firebase-login", response_model=TokenResponse)
async def firebase_login(req: FirebaseLoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticates via Firebase ID token, auto-provisioning workspace if new."""
    try:
        user, business, access_token = await firebase_auth_service.authenticate_firebase_user(
            db=db,
            id_token=req.id_token,
            business_name=req.business_name
        )
        return TokenResponse(
            access_token=access_token,
            user_id=user.id,
            business_id=business.id,
            role=user.role,
            business_name=business.name,
            business_slug=business.slug,
            share_token=business.share_token
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Firebase authentication error: {str(e)}"
        )

@router.get("/db-health")
async def check_db_health():
    """Checks database engine health, pooling status, and concurrency mode."""
    return await get_database_health()

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


@router.put("/rename-account")
async def rename_account(
    req: AccountRenameRequest,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Owner endpoint: Renames the business workspace/account."""
    biz_query = select(Business).where(Business.id == owner.business_id)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    new_name = req.business_name.strip()
    business.name = new_name
    await db.commit()
    await db.refresh(business)

    return {
        "status": "success",
        "message": "Account name updated successfully.",
        "business_id": business.id,
        "business_name": business.name,
        "business_slug": business.slug
    }


@router.put("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Authenticated user endpoint: Changes account password."""
    is_firebase_managed = (current_user.auth_provider == "firebase" and current_user.password_hash == "firebase_managed_auth")
    if not is_firebase_managed and current_user.password_hash:
        if not req.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is required to change password."
            )
        if not verify_password(req.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect."
            )

    current_user.password_hash = hash_password(req.new_password)
    await db.commit()
    await db.refresh(current_user)

    return {
        "status": "success",
        "message": "Password changed successfully. You can now use your new password to sign in."
    }


@router.delete("/delete-account")
async def delete_account(
    req: DeleteAccountRequest,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Owner endpoint: Permanently deletes the account and all business workspace data:
    - Cascades documents, chunks, tickets, chat sessions, feedback, and user profiles.
    - Purges vector chunks from ChromaDB and BM25 index.
    """
    if req.confirmation_phrase.strip().upper() != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation phrase mismatch. Please type exactly 'DELETE MY ACCOUNT' to confirm."
        )

    biz_id = owner.business_id
    biz_query = select(Business).where(Business.id == biz_id)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business workspace not found.")

    # 1. Purge vector stores
    try:
        await vector_store_service.delete_business(biz_id)
    except Exception as e:
        logger.warning(f"Note purging ChromaDB business {biz_id}: {e}")

    try:
        bm25_store_service.delete_business(biz_id)
    except Exception as e:
        logger.warning(f"Note purging BM25 business {biz_id}: {e}")

    # 2. Delete business entity (cascade deletes users, documents, tickets, chats via SQLAlchemy relationship)
    await db.delete(business)
    await db.commit()

    return {
        "status": "deleted",
        "message": "Business account, knowledge base, and all associated workspace data permanently deleted."
    }

