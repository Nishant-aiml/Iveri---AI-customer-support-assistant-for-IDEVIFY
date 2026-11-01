import os
import re
from typing import Tuple
from fastapi import HTTPException, status, UploadFile

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

def sanitize_filename(filename: str) -> str:
    """Sanitizes filename against path traversal and special characters."""
    if not filename:
        return "unnamed_document.txt"

    # 1. Strip any directory traversal components (both Unix / and Windows \)
    base = os.path.basename(filename).replace("\\", "/").split("/")[-1]

    # 2. Extract name and extension
    name, ext = os.path.splitext(base)
    ext = ext.lower().strip()

    # 3. Clean filename characters (letters, numbers, hyphens, underscores)
    clean_name = re.sub(r"[^\w\s\.-]", "_", name).strip()
    if not clean_name:
        clean_name = "document"

    # Avoid hidden files
    clean_name = clean_name.lstrip(".")

    return f"{clean_name}{ext}"


def verify_file_signature(header: bytes, ext: str) -> bool:
    """Inspects magic bytes to ensure file content matches the declared extension."""
    ext = ext.lower()

    if ext == ".pdf":
        return header.startswith(b"%PDF-")
    elif ext == ".docx":
        # DOCX files are ZIP packages starting with PK\x03\x04
        return header.startswith(b"PK\x03\x04")
    elif ext in [".txt", ".md"]:
        # Text files shouldn't contain null bytes
        if b"\x00" in header:
            return False
        try:
            header.decode("utf-8")
            return True
        except UnicodeDecodeError:
            try:
                header.decode("latin-1")
                return True
            except Exception:
                return False

    return True


async def read_and_validate_upload(file: UploadFile, max_bytes: int) -> Tuple[bytes, str, str]:
    """Safely reads upload stream, enforces max byte limit in memory,

    and validates magic byte signatures.
    
    Returns:
        Tuple[bytes, str, str]: (content_bytes, sanitized_filename, extension)
    """
    raw_filename = file.filename or "uploaded_document"
    clean_name = sanitize_filename(raw_filename)
    ext = os.path.splitext(clean_name)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Supported formats are: PDF, DOCX, TXT, MD."
        )

    # Read in controlled chunks to prevent memory/disk exhaustion
    content = bytearray()
    chunk_size = 1024 * 1024  # 1MB chunk
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of {max_bytes // (1024 * 1024)}MB."
            )

    bytes_data = bytes(content)

    # Check magic bytes on initial header (first 512 bytes)
    header = bytes_data[:512]
    if len(bytes_data) > 0 and not verify_file_signature(header, ext):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File signature mismatch. The content of '{clean_name}' does not match its '{ext}' extension."
        )

    return bytes_data, clean_name, ext
