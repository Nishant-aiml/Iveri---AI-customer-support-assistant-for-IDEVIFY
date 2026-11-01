from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from app.database import get_db
from app.models.business import Business
from app.models.user import User
from app.models.document import Document
from app.schemas.business import BusinessSettingsUpdateRequest, BusinessSettingsResponse, PublicBusinessInfoResponse
from app.utils.security import get_current_owner

router = APIRouter(tags=["Business Settings & Public"])

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
        fallback_message=business.fallback_message,
        starter_questions=business.starter_questions,
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
    if req.fallback_message is not None:
        business.fallback_message = req.fallback_message
    if req.starter_questions is not None:
        business.starter_questions = req.starter_questions

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
        fallback_message=business.fallback_message,
        starter_questions=business.starter_questions,
        shareable_link=shareable_link,
        embed_snippet=embed_snippet
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
        fallback_message=business.fallback_message,
        starter_questions=business.starter_questions,
        document_count=doc_count
    )
