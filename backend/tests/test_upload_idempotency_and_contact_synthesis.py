import os
import sys
import unittest
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.rrf import reciprocal_rank_fusion
from app.services.llm_client import llm_client
from app.services.circuit_breaker import circuit_breaker

class TestUploadIdempotencyAndContactSynthesis(unittest.IsolatedAsyncioTestCase):

    async def test_01_rrf_content_deduplication(self):
        """Verifies that RRF drops duplicate content chunks even when IDs differ."""
        dense = [
            {"id": "doc1_c1", "content": "Contact: Phone +91 20 5550 2468", "score": 0.88, "metadata": {}},
            {"id": "doc2_c1", "content": "Contact: Phone +91 20 5550 2468", "score": 0.87, "metadata": {}},  # Duplicate chunk from re-upload
            {"id": "doc1_c2", "content": "Clinic hours: Monday to Saturday", "score": 0.72, "metadata": {}},
        ]
        sparse = [
            {"id": "doc1_c1", "content": "Contact: Phone +91 20 5550 2468", "score": 3.0, "metadata": {}},
            {"id": "doc2_c1", "content": "Contact: Phone +91 20 5550 2468", "score": 2.9, "metadata": {}},
        ]

        fused = reciprocal_rank_fusion(dense, sparse, k=60, top_n=5)
        # Content must be deduplicated: exactly 2 distinct concepts returned, not 3
        self.assertEqual(len(fused), 2)
        contents = [f["content"] for f in fused]
        self.assertIn("Contact: Phone +91 20 5550 2468", contents)
        self.assertIn("Clinic hours: Monday to Saturday", contents)

    async def test_02_clean_contact_and_hours_synthesis(self):
        """Verifies that asking for contact number extracts clean contact info without overlap artifacts."""
        grounded_chunks = [
            {
                "id": "c1",
                "content": (
                    "Lakeview Dental Clinic - Patient Information Guide\n"
                    "About the Clinic\n"
                    "Lakeview Dental Clinic is located on Lake Road, Baner, Pune.\n"
                    "Clinic hours: Monday to Saturday, 9:00 AM to 1:00 PM and 4:00 PM to 8:00 PM. On Sundays\n"
                    "the clinic is open from 10:00 AM to 1:00 PM for emergencies only.\n"
                    "Contact: Phone +91 20 5550 2468, email appointments@lakeviewdental.example."
                ),
                "metadata": {"document_name": "Lakeview_Dental_Patient_Guide.pdf"}
            },
            {
                "id": "c2",
                # Overlap chunk with '... ' marker
                "content": (
                    "is open from 10:00 AM to 1:00 PM for emergencies only. ... Contact: Phone +91 20 5550 2468, email appointments@lakeviewdental.example.\n"
                    "Treatment Fees\n"
                    "Consultation Rs. 500"
                ),
                "metadata": {"document_name": "Lakeview_Dental_Patient_Guide.pdf"}
            }
        ]

        ans = llm_client._synthesize_grounded_extractive("what is the contact number", grounded_chunks)
        self.assertIn("+91 20 5550 2468", ans)
        self.assertIn("appointments@lakeviewdental.example", ans)
        # Ensure no overlap markers '...' leaked into final formatted answer
        self.assertNotIn("...", ans)
        # Ensure no repeated lines
        lines = [line.strip() for line in ans.split("\n") if line.strip()]
        self.assertEqual(len(lines), len(set(lines)), "Extracted output must not contain duplicate lines.")

    async def test_03_circuit_breaker_permits_contact_query(self):
        """Verifies circuit breaker correctly evaluates contact queries with grounded chunks."""
        fused_chunks = [
            {
                "id": "c1",
                "content": "Contact: Phone +91 20 5550 2468, email appointments@lakeviewdental.example.",
                "rrf_score": 0.85,
                "dense_similarity": 0.75,
                "sparse_score": 1.5,
                "metadata": {"document_name": "Lakeview_Dental_Patient_Guide.pdf"}
            }
        ]
        decision = circuit_breaker.evaluate(fused_chunks=fused_chunks, query="what is the contact number")
        self.assertTrue(decision["can_answer"])
        self.assertEqual(decision["reason"], "confident_match")

if __name__ == "__main__":
    unittest.main()
