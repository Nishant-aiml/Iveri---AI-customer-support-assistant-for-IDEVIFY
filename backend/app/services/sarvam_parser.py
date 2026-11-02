import logging
import httpx
from typing import List, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class SarvamDocumentIntelligenceClient:
    """Client for Sarvam AI's Document Intelligence and Digitization API.
    
    Provides high-accuracy OCR, reading order restoration, table preservation,
    and native support for English and 22 Indian languages.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, fallback_api_key: Optional[str] = None):
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.fallback_api_key = fallback_api_key or getattr(settings, "SARVAM_FALLBACK_API_KEY", "")
        self.base_url = (base_url or settings.SARVAM_API_URL).rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool((self.api_key and self.api_key.strip()) or (self.fallback_api_key and self.fallback_api_key.strip()))

    async def _execute_digitization(self, client: httpx.AsyncClient, url: str, key: str, file_path: str, file_name: str) -> List[Dict[str, Any]]:
        headers = {
            "api-subscription-key": key,
        }
        with open(file_path, "rb") as f:
            files = {"file": (file_name, f, "application/octet-stream")}
            response = await client.post(url, headers=headers, files=files)

        if response.status_code not in (200, 201, 202):
            logger.warning(
                f"Sarvam API responded with status {response.status_code}: {response.text[:200]}"
            )
            raise RuntimeError(f"Sarvam API error: HTTP {response.status_code}")

        data = response.json()
        pages: List[Dict[str, Any]] = []

        # Format 1: Direct pages array in response
        if "pages" in data and isinstance(data["pages"], list):
            for idx, page in enumerate(data["pages"]):
                text = page.get("text") or page.get("markdown") or ""
                pages.append({
                    "page_number": page.get("page_number", idx + 1),
                    "text": text.strip()
                })

        # Format 2: Combined markdown or text output
        elif "markdown" in data or "text" in data:
            full_text = data.get("markdown") or data.get("text") or ""
            pages.append({
                "page_number": 1,
                "text": full_text.strip()
            })

        if not pages or all(not p["text"] for p in pages):
            raise ValueError("Sarvam Document Intelligence returned empty text content.")

        return pages

    async def parse_document(self, file_path: str, file_name: str) -> List[Dict[str, Any]]:
        """Sends document to Sarvam AI Document Intelligence API with automatic key failover.
        
        Returns:
            List[Dict[str, Any]]: [{'page_number': int, 'text': str, 'layout': dict}]
        """
        if not self.is_configured:
            raise ValueError("Sarvam API key is not configured. Switching to local fallback parser.")

        url = f"{self.base_url}/doc-digitization/job/v1"
        logger.info(f"Submitting '{file_name}' to Sarvam Document Intelligence API...")

        async with httpx.AsyncClient(timeout=45.0) as client:
            # Try primary key
            if self.api_key and self.api_key.strip():
                try:
                    pages = await self._execute_digitization(client, url, self.api_key, file_path, file_name)
                    logger.info(f"Sarvam Document Intelligence (Primary) successfully extracted {len(pages)} pages from '{file_name}'.")
                    return pages
                except Exception as e:
                    logger.warning(f"Primary Sarvam Document Intelligence key failed ({str(e)}). Checking fallback key...")

            # Try fallback key if available
            if self.fallback_api_key and self.fallback_api_key.strip():
                try:
                    logger.info(f"Attempting Sarvam Document Intelligence with fallback key for '{file_name}'...")
                    pages = await self._execute_digitization(client, url, self.fallback_api_key, file_path, file_name)
                    logger.info(f"Sarvam Document Intelligence (Fallback Key) successfully extracted {len(pages)} pages from '{file_name}'.")
                    return pages
                except Exception as e:
                    logger.warning(f"Fallback Sarvam key also failed ({str(e)}). Switching to local PyMuPDF parser.")
                    raise e

        raise RuntimeError("Sarvam Document Intelligence failed on all configured API keys.")
