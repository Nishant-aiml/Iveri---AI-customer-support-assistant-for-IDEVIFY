import unittest
import os
import sys
import io
import openpyxl
from PIL import Image, ImageDraw

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import AsyncSessionLocal, init_db
from app.models.business import Business
from app.models.user import User
from app.utils.security import create_access_token
from app.utils.upload_validator import verify_file_signature, ALLOWED_EXTENSIONS
from app.services.fallback_parser import ExcelParser, ImageOCRParser, TesseractOCRParser
from app.services.document_parser import document_parser_service

class TestMultiDocExcelOCR(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

        unique_suffix = os.urandom(3).hex()
        async with AsyncSessionLocal() as db:
            self.biz = Business(
                name="Brew & Byte Cafe",
                slug=f"brew-byte-{unique_suffix}",
                welcome_message="Welcome to Brew & Byte!",
                fallback_message="Sorry, no data available."
            )
            db.add(self.biz)
            await db.flush()

            self.owner = User(
                business_id=self.biz.id,
                email=f"owner_{unique_suffix}@brewbyte.com",
                password_hash="test_pw_hash",
                role="owner"
            )
            db.add(self.owner)
            await db.commit()
            await db.refresh(self.biz)
            await db.refresh(self.owner)

            self.biz_id = self.biz.id
            self.owner_token = create_access_token({
                "sub": self.owner.id,
                "email": self.owner.email,
                "business_id": self.biz_id
            })
            self.auth_headers = {"Authorization": f"Bearer {self.owner_token}"}

    async def asyncTearDown(self):
        await self.client.aclose()

    def test_upload_validator_signatures(self):
        """Validates extension expansion and magic-byte signature detection."""
        # 1. Allowed extensions include Excel and Images
        self.assertIn(".xlsx", ALLOWED_EXTENSIONS)
        self.assertIn(".xls", ALLOWED_EXTENSIONS)
        self.assertIn(".png", ALLOWED_EXTENSIONS)
        self.assertIn(".jpg", ALLOWED_EXTENSIONS)
        self.assertIn(".webp", ALLOWED_EXTENSIONS)

        # 2. Excel magic bytes (ZIP header PK\x03\x04)
        valid_xlsx_header = b"PK\x03\x04\x14\x00\x06\x00"
        self.assertTrue(verify_file_signature(valid_xlsx_header, ".xlsx"))

        # 3. PNG magic bytes
        valid_png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        self.assertTrue(verify_file_signature(valid_png_header, ".png"))

        # 4. Corrupted signature rejection
        bad_xlsx_header = b"INVALID_ZIP_HEADER"
        self.assertFalse(verify_file_signature(bad_xlsx_header, ".xlsx"))

    def test_excel_parser_structured_markdown(self):
        """Tests that ExcelParser extracts sheets, markdown tables, and row breakdowns."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Coffee_Catalog"
        ws.append(["SKU", "Product_Name", "Price", "Category"])
        ws.append(["BB-101", "Ethiopian Yirgacheffe", "$16.50", "Single Origin"])
        ws.append(["BB-102", "Colombian Supremo", "$14.00", "Dark Roast"])

        temp_path = "temp_test_catalog.xlsx"
        try:
            wb.save(temp_path)
            wb.close()

            pages = ExcelParser.parse(temp_path)
            self.assertEqual(len(pages), 1)
            text = pages[0]["text"]
            self.assertIn("## Excel Sheet: Coffee_Catalog", text)
            self.assertIn("Ethiopian Yirgacheffe", text)
            self.assertIn("Colombian Supremo", text)
            self.assertIn("- Row 1: SKU: BB-101 | Product_Name: Ethiopian Yirgacheffe", text)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_image_ocr_parser_tesseract(self):
        """Tests that Tesseract OCR extracts text from an in-memory generated image."""
        img = Image.new("RGB", (400, 80), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((15, 30), "Store Hours: 9am to 6pm", fill=(0, 0, 0))

        temp_img_path = "temp_ocr_test.png"
        try:
            img.save(temp_img_path)
            pages = ImageOCRParser.parse(temp_img_path)
            self.assertGreaterEqual(len(pages), 1)
            text = pages[0]["text"].lower()
            self.assertTrue("store" in text or "hours" in text or "9am" in text)
        finally:
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

    async def test_unified_document_parser_routing(self):
        """Verifies that UnifiedDocumentParserService routes Excel and Image files properly."""
        # Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Inventory"
        ws.append(["Item", "Stock"])
        ws.append(["Oat Milk", "45 Cartons"])
        xlsx_path = "temp_route_test.xlsx"
        wb.save(xlsx_path)
        wb.close()

        try:
            pages, engine = await document_parser_service.parse(xlsx_path, "inventory.xlsx")
            self.assertEqual(engine, "excel_openpyxl")
            self.assertIn("Oat Milk", pages[0]["text"])
        finally:
            if os.path.exists(xlsx_path):
                os.remove(xlsx_path)

    async def test_single_document_upload_backward_compatibility(self):
        """Verifies that uploading a single file with field name 'file' returns 202 and DocumentUploadResponse."""
        content = b"Single document test content about store return policies."
        files = {
            "file": ("return_policy.txt", content, "text/plain")
        }
        res = await self.client.post("/api/documents/upload", headers=self.auth_headers, files=files)
        self.assertEqual(res.status_code, 202)
        data = res.json()
        self.assertEqual(data["status"], "QUEUED")
        self.assertTrue(data["document_id"])
        self.assertEqual(data["total_queued"], 1)

    async def test_multi_document_batch_upload_api(self):
        """Verifies that multiple documents can be uploaded simultaneously in a single HTTP request."""
        # 1. Create in-memory Excel file
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Pricing"
        ws.append(["Item", "Price"])
        ws.append(["Latte", "$4.50"])
        excel_buf = io.BytesIO()
        wb.save(excel_buf)
        excel_bytes = excel_buf.getvalue()

        # 2. Create in-memory Image file
        img = Image.new("RGB", (200, 60), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((10, 20), "Wifi Password: LatteArt", fill=(0, 0, 0))
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        img_bytes = img_buf.getvalue()

        # 3. Post multiple files
        multi_files = [
            ("files", ("menu_pricing.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ("files", ("wifi_board.png", img_bytes, "image/png"))
        ]

        res = await self.client.post("/api/documents/upload", headers=self.auth_headers, files=multi_files)
        self.assertEqual(res.status_code, 202)
        data = res.json()
        self.assertEqual(data["status"], "QUEUED")
        self.assertEqual(data["total_queued"], 2)
        self.assertEqual(len(data["uploaded_files"]), 2)
        self.assertIn("2 documents uploaded successfully", data["message"])

    async def test_batch_upload_alias_endpoint(self):
        """Verifies that /api/documents/batch-upload functions identically for batch ingestion."""
        file_1 = ("doc1.txt", b"First batch item facts", "text/plain")
        file_2 = ("doc2.txt", b"Second batch item facts", "text/plain")
        multi_files = [
            ("files", file_1),
            ("files", file_2)
        ]

        res = await self.client.post("/api/documents/batch-upload", headers=self.auth_headers, files=multi_files)
        self.assertEqual(res.status_code, 202)
        data = res.json()
        self.assertEqual(data["total_queued"], 2)
