import os
import logging
from typing import List, Dict, Any, Tuple
from app.services.sarvam_parser import SarvamDocumentIntelligenceClient
from app.services.fallback_parser import (
    PyMuPDFFallbackParser,
    DocxParser,
    PlainTextParser,
    ExcelParser,
    ImageOCRParser,
    DoclingParser
)

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
EXCEL_EXTENSIONS = {".xlsx", ".xls"}

class UnifiedDocumentParserService:
    """Unified document parsing service implementing:
    
    1. Primary: Sarvam Document Intelligence API (complex tables, layout, multilingual)
    2. Docling Engine: High-fidelity layout preservation, tables, and AI OCR
    3. Tesseract OCR: Fast local optical character recognition for images
    4. openpyxl & pandas: Tabular Excel spreadsheet parser (.xlsx, .xls)
    5. PyMuPDF (fitz): High-speed streamed PDF parser (1,000+ pages)
    6. Dedicated DOCX and TXT parsers
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
            # Tier 1: Sarvam Document Intelligence API
            if self.sarvam_client.is_configured:
                try:
                    pages = await self.sarvam_client.parse_document(file_path, file_name)
                    return pages, "sarvam"
                except Exception as e:
                    logger.warning(
                        f"Sarvam Document Intelligence failed ({str(e)}). "
                        f"Attempting Docling / PyMuPDF fallback..."
                    )
            
            # Tier 2: Docling document parser
            try:
                pages = DoclingParser.parse(file_path)
                return pages, "docling"
            except Exception as e:
                logger.info(f"Docling PDF parsing skipped ({e}). Engaging PyMuPDF...")

            # Tier 3: PyMuPDF local fallback
            pages = PyMuPDFFallbackParser.parse(file_path)
            return pages, "pymupdf"

        elif ext == ".docx":
            try:
                pages = DoclingParser.parse(file_path)
                return pages, "docling"
            except Exception:
                pass
            pages = DocxParser.parse(file_path)
            return pages, "docx"

        elif ext in EXCEL_EXTENSIONS:
            pages = ExcelParser.parse(file_path)
            return pages, "excel_openpyxl"

        elif ext in IMAGE_EXTENSIONS:
            pages = ImageOCRParser.parse(file_path)
            return pages, "ocr_engine"

        elif ext in (".txt", ".md"):
            pages = PlainTextParser.parse(file_path)
            return pages, "txt"

        else:
            raise ValueError(f"Unsupported file format '{ext}'.")

    def stream_parse(self, file_path: str, file_name: str, batch_size: int = 25):
        """Streams document pages in memory-efficient batches to support 1,000+ page documents.
        
        Yields:
            Tuple[List[Dict[str, Any]], int, int, str]: 
            (page_batch, processed_count, total_count, parser_used)
        """
        ext = os.path.splitext(file_name)[1].lower()

        if ext == ".pdf":
            for batch, processed, total in PyMuPDFFallbackParser.stream_pages(file_path, batch_size=batch_size):
                yield batch, processed, total, "pymupdf"
        elif ext == ".docx":
            pages = DocxParser.parse(file_path)
            yield pages, len(pages), len(pages), "docx"
        elif ext in EXCEL_EXTENSIONS:
            for batch, processed, total in ExcelParser.stream_pages(file_path, batch_size=batch_size):
                yield batch, processed, total, "excel_openpyxl"
        elif ext in IMAGE_EXTENSIONS:
            for batch, processed, total in ImageOCRParser.stream_pages(file_path, batch_size=batch_size):
                yield batch, processed, total, "ocr_engine"
        elif ext in (".txt", ".md"):
            pages = PlainTextParser.parse(file_path)
            yield pages, len(pages), len(pages), "txt"
        else:
            raise ValueError(f"Unsupported file format '{ext}'.")

document_parser_service = UnifiedDocumentParserService()
