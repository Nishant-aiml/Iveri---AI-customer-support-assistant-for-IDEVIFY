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
    def get_page_count(file_path: str) -> int:
        """Returns the total number of pages in the PDF document."""
        try:
            import fitz
        except ImportError:
            raise ImportError("PyMuPDF (fitz) is not installed. Run `pip install PyMuPDF`.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found at: {file_path}")

        doc = fitz.open(file_path)
        try:
            return len(doc)
        finally:
            doc.close()

    @staticmethod
    def stream_pages(file_path: str, batch_size: int = 25):
        """Streams pages in memory-efficient batches to support 1,000+ page documents without memory exhaustion.
        
        Yields:
            Tuple[List[Dict[str, Any]], int, int]: (batch_pages, processed_pages_so_far, total_pages)
        """
        try:
            import fitz
        except ImportError:
            raise ImportError("PyMuPDF (fitz) is not installed. Run `pip install PyMuPDF`.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found at: {file_path}")

        doc = fitz.open(file_path)
        total_pages = len(doc)

        try:
            batch: List[Dict[str, Any]] = []
            for page_index in range(total_pages):
                page = doc[page_index]
                text = page.get_text("text").strip()
                if text:
                    batch.append({
                        "page_number": page_index + 1,
                        "text": text
                    })

                # Yield batch when limit reached or at the very end
                if len(batch) >= batch_size:
                    yield batch, page_index + 1, total_pages
                    batch = []

            if batch:
                yield batch, total_pages, total_pages
        finally:
            doc.close()

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


class ExcelParser:
    """Extracts tabular structured data and natural-language row facts from Excel (.xlsx, .xls) spreadsheets."""

    @staticmethod
    def parse(file_path: str) -> List[Dict[str, Any]]:
        pages: List[Dict[str, Any]] = []
        ext = os.path.splitext(file_path)[1].lower()

        # 1. Primary engine for .xlsx: openpyxl
        if ext == ".xlsx":
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
                for sheet_idx, sheet_name in enumerate(wb.sheetnames):
                    ws = wb[sheet_name]
                    rows_data = []
                    for row in ws.iter_rows(values_only=True):
                        if any(cell is not None and str(cell).strip() != "" for cell in row):
                            rows_data.append([str(c).strip() if c is not None else "" for c in row])

                    if not rows_data:
                        continue

                    headers = rows_data[0]
                    headers = [h if h else f"Column_{i+1}" for i, h in enumerate(headers)]
                    data_rows = rows_data[1:]

                    sheet_lines = [f"## Excel Sheet: {sheet_name}\n"]
                    # Render Markdown Table
                    sheet_lines.append("| " + " | ".join(headers) + " |")
                    sheet_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                    for r in data_rows[:250]:
                        padded = r + [""] * max(0, len(headers) - len(r))
                        sheet_lines.append("| " + " | ".join(padded[:len(headers)]) + " |")

                    # Render Semantic Row Summaries for Dense RAG Search
                    sheet_lines.append("\n### Row Data Breakdown:\n")
                    for r_idx, r in enumerate(data_rows, start=1):
                        padded = r + [""] * max(0, len(headers) - len(r))
                        pairs = [f"{h}: {v}" for h, v in zip(headers, padded) if v]
                        if pairs:
                            sheet_lines.append(f"- Row {r_idx}: " + " | ".join(pairs))

                    full_text = "\n".join(sheet_lines).strip()
                    if full_text:
                        pages.append({
                            "page_number": sheet_idx + 1,
                            "text": full_text
                        })
                wb.close()
            except Exception as e:
                logger.warning(f"openpyxl failed for {file_path} ({e}). Falling back to pandas...")
                pages = []

        # 2. Fallback / legacy engine (.xls, or fallback from openpyxl): pandas
        if not pages:
            try:
                import pandas as pd
                with pd.ExcelFile(file_path) as ef:
                    for sheet_idx, sheet_name in enumerate(ef.sheet_names):
                        df = pd.read_excel(ef, sheet_name=sheet_name)
                        df = df.dropna(how="all")
                        if df.empty:
                            continue

                        md_table = df.to_markdown(index=False)
                        rows_summary = []
                        for idx, row in df.iterrows():
                            row_pairs = [f"{col}: {val}" for col, val in row.items() if pd.notna(val) and str(val).strip()]
                            if row_pairs:
                                rows_summary.append(f"- Row {idx+1}: " + " | ".join(row_pairs))

                        content = f"## Excel Sheet: {sheet_name}\n\n{md_table}\n\n### Row Breakdown:\n" + "\n".join(rows_summary)
                        pages.append({
                            "page_number": sheet_idx + 1,
                            "text": content.strip()
                        })
            except Exception as e:
                logger.error(f"Pandas Excel reading failed ({e})")

        if not pages:
            raise ValueError(f"No readable data could be extracted from spreadsheet '{os.path.basename(file_path)}'.")

        return pages

    @staticmethod
    def stream_pages(file_path: str, batch_size: int = 25):
        pages = ExcelParser.parse(file_path)
        total = len(pages)
        for i in range(0, total, batch_size):
            batch = pages[i:i + batch_size]
            yield batch, min(i + batch_size, total), total


class DoclingParser:
    """Document Intelligence and layout analysis parser using Docling."""
    _converter = None

    @classmethod
    def get_converter(cls):
        if cls._converter is None:
            from docling.document_converter import DocumentConverter
            cls._converter = DocumentConverter()
        return cls._converter

    @classmethod
    def parse(cls, file_path: str) -> List[Dict[str, Any]]:
        converter = cls.get_converter()
        conv_res = converter.convert(file_path)
        md_text = conv_res.document.export_to_markdown()
        if not md_text or not md_text.strip():
            raise ValueError("Docling produced empty document text.")
        return [{
            "page_number": 1,
            "text": md_text.strip()
        }]


class TesseractOCRParser:
    """Optical Character Recognition for image documents using Tesseract OCR."""

    @staticmethod
    def _get_tesseract_cmd() -> str | None:
        import shutil
        cmd = shutil.which("tesseract")
        if cmd:
            return cmd
        candidates = [
            os.environ.get("TESSERACT_PATH"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract"
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    @classmethod
    def parse(cls, file_path: str) -> List[Dict[str, Any]]:
        try:
            import pytesseract
            from PIL import Image, ImageEnhance
        except ImportError:
            raise ImportError("pytesseract or Pillow is not installed.")

        tess_cmd = cls._get_tesseract_cmd()
        if tess_cmd:
            pytesseract.pytesseract.tesseract_cmd = tess_cmd

        img = Image.open(file_path)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        text = pytesseract.image_to_string(img)
        if not text.strip():
            # Try mild contrast enhancement
            enhancer = ImageEnhance.Contrast(img.convert("L"))
            enhanced = enhancer.enhance(1.6)
            text = pytesseract.image_to_string(enhanced)

        clean_text = text.strip()
        if not clean_text:
            raise ValueError(f"Tesseract OCR found no readable text in image '{os.path.basename(file_path)}'.")

        return [{
            "page_number": 1,
            "text": f"## Image OCR Document: {os.path.basename(file_path)}\n\n{clean_text}"
        }]


class ImageOCRParser:
    """Hybrid image parser using fast local Tesseract OCR with Docling layout fallback."""

    @staticmethod
    def parse(file_path: str) -> List[Dict[str, Any]]:
        # 1. Primary engine for images: High-speed local Tesseract OCR (zero network latency)
        try:
            pages = TesseractOCRParser.parse(file_path)
            if pages and pages[0].get("text", "").strip():
                logger.info(f"Tesseract OCR extracted text from {os.path.basename(file_path)}")
                return pages
        except Exception as e:
            logger.info(f"Tesseract OCR skipped or yielded no text ({e}). Trying Docling...")

        # 2. Secondary engine: Docling (AI layout and text analysis)
        try:
            pages = DoclingParser.parse(file_path)
            if pages and pages[0].get("text", "").strip():
                logger.info(f"Docling successfully extracted layout/text from {os.path.basename(file_path)}")
                return pages
        except Exception as e:
            logger.warning(f"Docling image extraction failed ({e})")

        raise ValueError(f"Could not extract any readable text from image '{os.path.basename(file_path)}'.")

    @staticmethod
    def stream_pages(file_path: str, batch_size: int = 25):
        pages = ImageOCRParser.parse(file_path)
        total = len(pages)
        for i in range(0, total, batch_size):
            batch = pages[i:i + batch_size]
            yield batch, min(i + batch_size, total), total

