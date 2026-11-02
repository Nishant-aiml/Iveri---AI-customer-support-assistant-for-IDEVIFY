from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List

class DocumentResponse(BaseModel):
    id: str
    business_id: str
    file_name: str
    file_type: str
    file_size_bytes: int
    chunk_count: int
    total_pages: int = 0
    processed_pages: int = 0
    processing_progress: int = 0
    status: str
    parser_used: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class DocumentUploadItem(BaseModel):
    document_id: str
    file_name: str
    status: str
    message: str

class DocumentUploadResponse(BaseModel):
    document_id: Optional[str] = None
    file_name: Optional[str] = None
    status: str
    message: str
    uploaded_files: Optional[List[DocumentUploadItem]] = None
    total_queued: int = 1

class ManualQACreateRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500, description="The customer question")
    answer: str = Field(..., min_length=3, max_length=3000, description="The verified answer to add to knowledge base")
    category: Optional[str] = Field("General", max_length=100)
    unanswered_question_id: Optional[str] = Field(None, description="Optional ID of the unanswered question being resolved")

class ManualQAResponse(BaseModel):
    document_id: str
    chunk_id: str
    question: str
    status: str
    message: str
