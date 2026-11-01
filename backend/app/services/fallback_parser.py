import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class PyMuPDFFallbackParser:
    """High-speed local PDF parser using PyMuPDF (fitz).
    
    Extracts text page by page with coordinates and reading order,
    operating with zero network dependency and zero memory overhead.
    """

    @staticmethod
    def parse(file_path: str) -> List[Dict[str, Any]]:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF (fitz) is not installed. Run `pip install PyMuPDF`.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found at: {file_path}")

        pages: List[Dict[str, Any]] = []
        doc = fitz.open(file_path)

        try:
            for page_index in range(len(doc)):
                page = doc[page_index]
                text = page.get_text("text").strip()
                if text:
                    pages.append({
                        "page_number": page_index + 1,
                        "text": text
                    })
        finally:
            doc.close()

        if not pages:
            raise ValueError("PyMuPDF was unable to extract any readable text from this document.")

        logger.info(f"PyMuPDF extracted {len(pages)} pages from {os.path.basename(file_path)}.")
        return pages


class DocxParser:
    """Extracts text and tables from Microsoft Word (.docx) documents."""

    @staticmethod
    def parse(file_path: str) -> List[Dict[str, Any]]:
        try:
            import docx
        except ImportError:
            raise ImportError("python-docx is not installed. Run `pip install python-docx`.")

        doc = docx.Document(file_path)
        full_text: List[str] = []

        # Extract paragraphs
        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text.strip())

        # Extract tables
        for table in doc.tables:
            for row in table.rows:
                row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_text:
                    full_text.append(" | ".join(row_text))

        combined_text = "\n\n".join(full_text)
        if not combined_text.strip():
            raise ValueError("No text could be extracted from this DOCX file.")

        return [{
            "page_number": 1,
            "text": combined_text
        }]


class PlainTextParser:
    """Extracts text from plaintext (.txt) documents with multi-encoding fallback."""

    @staticmethod
    def parse(file_path: str) -> List[Dict[str, Any]]:
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
        content = ""

        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, Exception):
                continue

        if not content.strip():
            raise ValueError("Unable to read plaintext file with standard encodings.")

        return [{
            "page_number": 1,
            "text": content.strip()
        }]
