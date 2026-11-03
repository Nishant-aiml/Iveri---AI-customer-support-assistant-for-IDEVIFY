import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from app.config import settings
from app.database import get_db
from app.models.business import Business
from app.models.user import User
from app.models.document import Document
from app.schemas.business import BusinessSettingsUpdateRequest, BusinessSettingsResponse, PublicBusinessInfoResponse
from app.utils.security import get_current_owner

router = APIRouter(tags=["Business Settings & Public"])

AVATARS_DIR = os.path.join(settings.UPLOAD_DIRECTORY, "avatars")
os.makedirs(AVATARS_DIR, exist_ok=True)

@router.get("/api/business/settings", response_model=BusinessSettingsResponse)
async def get_business_settings(owner: User = Depends(get_current_owner), db: AsyncSession = Depends(get_db)):
    """Owner endpoint: Retrieves current business settings, shareable link, and embed widget code."""
    biz_query = select(Business).where(Business.id == owner.business_id)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    shareable_link = f"/chat/{business.slug}"
    embed_snippet = f'<script src="https://app.idevify.com/widget.js" data-business="{business.slug}" defer></script>'

    return BusinessSettingsResponse(
        id=business.id,
        name=business.name,
        slug=business.slug,
        share_token=business.share_token,
        tone=business.tone,
        brand_color=business.brand_color,
        avatar_url=business.avatar_url or "",
        widget_position=business.widget_position or "bottom-right",
        welcome_message=business.welcome_message or "Hello! How can I help you today?",
        custom_prompt=getattr(business, "custom_prompt", "") or "",
        fallback_message=business.fallback_message,
        starter_questions=business.starter_questions,
        whatsapp_number=business.whatsapp_number or "",
        enable_whatsapp=getattr(business, "enable_whatsapp", True) if getattr(business, "enable_whatsapp", None) is not None else True,
        enable_callback=getattr(business, "enable_callback", True) if getattr(business, "enable_callback", None) is not None else True,
        callback_channel=getattr(business, "callback_channel", "phone_and_email") or "phone_and_email",
        callback_button_text=getattr(business, "callback_button_text", "Request Callback") or "Request Callback",
        show_sources=getattr(business, "show_sources", True) if getattr(business, "show_sources", None) is not None else True,
        shareable_link=shareable_link,
        embed_snippet=embed_snippet
    )

@router.put("/api/business/settings", response_model=BusinessSettingsResponse)
async def update_business_settings(
    req: BusinessSettingsUpdateRequest,
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Owner endpoint: Updates assistant customization, branding colors, avatar, position, tone, and starter questions."""
    biz_query = select(Business).where(Business.id == owner.business_id)
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    if req.name is not None:
        business.name = req.name
    if req.tone is not None:
        business.tone = req.tone
    if req.brand_color is not None:
        business.brand_color = req.brand_color
    if req.avatar_url is not None:
        business.avatar_url = req.avatar_url
    if req.widget_position is not None:
        business.widget_position = req.widget_position
    if req.welcome_message is not None:
        business.welcome_message = req.welcome_message
    if req.custom_prompt is not None:
        business.custom_prompt = req.custom_prompt
    if req.fallback_message is not None:
        business.fallback_message = req.fallback_message
    if req.starter_questions is not None:
        business.starter_questions = req.starter_questions
    if req.whatsapp_number is not None:
        business.whatsapp_number = req.whatsapp_number.strip()
    if req.enable_whatsapp is not None:
        business.enable_whatsapp = req.enable_whatsapp
    if req.enable_callback is not None:
        business.enable_callback = req.enable_callback
    if req.callback_channel is not None:
        business.callback_channel = req.callback_channel
    if req.callback_button_text is not None:
        business.callback_button_text = req.callback_button_text.strip()
    if req.show_sources is not None:
        business.show_sources = req.show_sources

    await db.commit()
    await db.refresh(business)

    shareable_link = f"/chat/{business.slug}"
    embed_snippet = f'<script src="https://app.idevify.com/widget.js" data-business="{business.slug}" defer></script>'

    return BusinessSettingsResponse(
        id=business.id,
        name=business.name,
        slug=business.slug,
        share_token=business.share_token,
        tone=business.tone,
        brand_color=business.brand_color,
        avatar_url=business.avatar_url or "",
        widget_position=business.widget_position or "bottom-right",
        welcome_message=business.welcome_message or "Hello! How can I help you today?",
        custom_prompt=getattr(business, "custom_prompt", "") or "",
        fallback_message=business.fallback_message,
        starter_questions=business.starter_questions,
        whatsapp_number=business.whatsapp_number or "",
        enable_whatsapp=getattr(business, "enable_whatsapp", True) if getattr(business, "enable_whatsapp", None) is not None else True,
        enable_callback=getattr(business, "enable_callback", True) if getattr(business, "enable_callback", None) is not None else True,
        callback_channel=getattr(business, "callback_channel", "phone_and_email") or "phone_and_email",
        callback_button_text=getattr(business, "callback_button_text", "Request Callback") or "Request Callback",
        show_sources=getattr(business, "show_sources", True) if getattr(business, "show_sources", None) is not None else True,
        shareable_link=shareable_link,
        embed_snippet=embed_snippet
    )

@router.post("/api/business/avatar/upload")
async def upload_business_avatar(
    file: UploadFile = File(...),
    owner: User = Depends(get_current_owner),
    db: AsyncSession = Depends(get_db)
):
    """Owner endpoint: Upload custom chatbot avatar DP directly from local device."""
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/webp", "image/svg+xml", "image/gif"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Please upload a PNG, JPEG, WEBP, GIF, or SVG image."
        )

    file_bytes = await file.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar image size exceeds 5MB limit."
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    if not ext or ext not in [".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"]:
        ext = ".png"

    filename = f"{owner.business_id}_{uuid.uuid4().hex[:10]}{ext}"
    file_path = os.path.join(AVATARS_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    avatar_url = f"/api/business/avatar/{filename}"

    biz_res = await db.execute(select(Business).where(Business.id == owner.business_id))
    business = biz_res.scalar_one_or_none()
    if business:
        business.avatar_url = avatar_url
        await db.commit()
        await db.refresh(business)

    return {"avatar_url": avatar_url, "message": "Avatar uploaded successfully."}

@router.get("/api/business/avatar/{filename}")
async def get_business_avatar(filename: str):
    """Public endpoint: Serves uploaded business chatbot avatar images."""
    clean_filename = os.path.basename(filename)
    file_path = os.path.join(AVATARS_DIR, clean_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar image not found.")

    ext = os.path.splitext(clean_filename)[1].lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".gif": "image/gif"
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(
        file_path,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )

@router.get("/api/public/business/{slug_or_token}", response_model=PublicBusinessInfoResponse)
async def get_public_business_info(slug_or_token: str, db: AsyncSession = Depends(get_db)):
    """Unauthenticated public endpoint: Resolves business branding for customer chat page or embeddable widget."""
    biz_query = select(Business).where(
        (Business.slug == slug_or_token) | (Business.share_token == slug_or_token)
    )
    business = (await db.execute(biz_query)).scalar_one_or_none()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business assistant not found. Please verify the link or widget key."
        )

    # Count indexed documents
    doc_count_query = select(func.count(Document.id)).where(
        Document.business_id == business.id,
        Document.status == "INDEXED"
    )
    doc_count = (await db.execute(doc_count_query)).scalar() or 0

    return PublicBusinessInfoResponse(
        id=business.id,
        name=business.name,
        slug=business.slug,
        tone=business.tone,
        brand_color=business.brand_color,
        avatar_url=business.avatar_url or "",
        widget_position=business.widget_position or "bottom-right",
        welcome_message=business.welcome_message or "Hello! How can I help you today?",
        custom_prompt=getattr(business, "custom_prompt", "") or "",
        fallback_message=business.fallback_message,
        starter_questions=business.starter_questions,
        whatsapp_number=business.whatsapp_number or "",
        enable_whatsapp=getattr(business, "enable_whatsapp", True) if getattr(business, "enable_whatsapp", None) is not None else True,
        enable_callback=getattr(business, "enable_callback", True) if getattr(business, "enable_callback", None) is not None else True,
        callback_channel=getattr(business, "callback_channel", "phone_and_email") or "phone_and_email",
        callback_button_text=getattr(business, "callback_button_text", "Request Callback") or "Request Callback",
        show_sources=getattr(business, "show_sources", True) if getattr(business, "show_sources", None) is not None else True,
        document_count=doc_count
    )
