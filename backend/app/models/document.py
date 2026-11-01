import json
from sqlalchemy import Column, String, Integer, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid

class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    business_id = Column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # 'pdf', 'docx', 'txt', 'manual_qa'
    storage_path = Column(String(512), nullable=True)
    file_size_bytes = Column(Integer, default=0, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="QUEUED", nullable=False)  # 'QUEUED', 'PROCESSING', 'INDEXED', 'FAILED'
    parser_used = Column(String(50), default="pending", nullable=False)  # 'sarvam', 'pymupdf', 'docx', 'txt', 'manual'
    error_message = Column(Text, nullable=True)

    business = relationship("Business", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    business_id = Column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, default=1, nullable=False)
    content = Column(Text, nullable=False)
    _metadata = Column("metadata", Text, default="{}", nullable=False)

    document = relationship("Document", back_populates="chunks")

    @property
    def metadata(self):
        try:
            return json.loads(self._metadata) if self._metadata else {}
        except Exception:
            return {}

    @metadata.setter
    def metadata(self, value):
        if isinstance(value, dict):
            self._metadata = json.dumps(value)
        else:
            self._metadata = json.dumps({})
