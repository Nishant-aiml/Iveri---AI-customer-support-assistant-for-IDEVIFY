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

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.base_url = (base_url or settings.SARVAM_API_URL).rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def parse_document(self, file_path: str, file_name: str) -> List[Dict[str, Any]]:
        """Sends document to Sarvam AI Document Intelligence API and returns structured page contents.
        
        Returns:
            List[Dict[str, Any]]: [{'page_number': int, 'text': str, 'layout': dict}]
        """
        if not self.is_configured:
            raise ValueError("Sarvam API key is not configured. Switching to local fallback parser.")

        headers = {
            "api-subscription-key": self.api_key,
        }

        # Sarvam doc-digitization API endpoint
        url = f"{self.base_url}/doc-digitization/job/v1"

        logger.info(f"Submitting '{file_name}' to Sarvam Document Intelligence API...")

        async with httpx.AsyncClient(timeout=45.0) as client:
            with open(file_path, "rb") as f:
                files = {"file": (file_name, f, "application/octet-stream")}
                response = await client.post(url, headers=headers, files=files)

            if response.status_code not in (200, 201, 202):
                logger.warning(
                    f"Sarvam API responded with status {response.status_code}: {response.text[:200]}"
                )
                raise RuntimeError(f"Sarvam API error: HTTP {response.status_code}")

            data = response.json()

            # Handle direct structured response or completed job
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

            logger.info(f"Sarvam Document Intelligence successfully extracted {len(pages)} pages from '{file_name}'.")
            return pages
