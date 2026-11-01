import os
import logging
from typing import List, Dict, Any, Tuple
from app.services.sarvam_parser import SarvamDocumentIntelligenceClient
from app.services.fallback_parser import PyMuPDFFallbackParser, DocxParser, PlainTextParser

logger = logging.getLogger(__name__)

class UnifiedDocumentParserService:
    """Unified document parsing service implementing:
    
    1. Primary: Sarvam Document Intelligence API (complex tables, layout, multilingual)
    2. Fallback: Local PyMuPDF (fitz) for PDF
    3. Dedicated parsers for DOCX and TXT
    """

    def __init__(self):
        self.sarvam_client = SarvamDocumentIntelligenceClient()

    async def parse(self, file_path: str, file_name: str) -> Tuple[List[Dict[str, Any]], str]:
        """Parses a document file and returns (pages, parser_used).
        
        Args:
            file_path: Local path to saved file
            file_name: Original file name
            
        Returns:
            Tuple[List[Dict[str, Any]], str]: (list of {'page_number': int, 'text': str}, parser_used_name)
        """
        ext = os.path.splitext(file_name)[1].lower()

        if ext == ".pdf":
            # Attempt 1: Sarvam Document Intelligence API
            if self.sarvam_client.is_configured:
                try:
                    pages = await self.sarvam_client.parse_document(file_path, file_name)
                    return pages, "sarvam"
                except Exception as e:
                    logger.warning(
                        f"Sarvam Document Intelligence failed ({str(e)}). "
                        f"Engaging local PyMuPDF fallback parser immediately..."
                    )
            
            # Attempt 2: PyMuPDF local fallback
            pages = PyMuPDFFallbackParser.parse(file_path)
            return pages, "pymupdf"

        elif ext == ".docx":
            pages = DocxParser.parse(file_path)
            return pages, "docx"

        elif ext in (".txt", ".md"):
            pages = PlainTextParser.parse(file_path)
            return pages, "txt"

        else:
            raise ValueError(f"Unsupported file format '{ext}'. Only PDF, DOCX, and TXT are supported.")

document_parser_service = UnifiedDocumentParserService()
