import os
import re
import unittest

class TestUiTabContracts(unittest.TestCase):
    """Verifies that the single-page application UI maintains strict settings sub-tab hierarchy,

    interactive RAG testing under settings, document inspection modal, and deletion controls.
    """

    def setUp(self):
        html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "static", "index.html"))
        with open(html_path, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_01_top_nav_tabs_exist(self):
        """Ensures Settings and RAG Playground navigation elements exist."""
        self.assertIn('id="tab-settings"', self.html)
        self.assertIn('id="tab-playground"', self.html)
        self.assertIn('switchTab(\'settings\')', self.html)
        self.assertIn('switchTab(\'playground\')', self.html)

    def test_02_settings_subtabs_and_testing_rag_embedded(self):
        """Ensures that under Settings, a dedicated 'Testing RAG' sub-tab houses the RAG Playground."""
        settings_match = re.search(r'<section\s+id="view-settings"[^>]*>(.*?)</section>', self.html, re.DOTALL)
        self.assertIsNotNone(settings_match, "view-settings section must exist.")
        settings_content = settings_match.group(1)

        # Sub-tab buttons
        self.assertIn('id="subtab-btn-testing-rag"', settings_content)
        self.assertIn('id="subtab-btn-studio"', settings_content)
        self.assertIn('id="subtab-btn-account"', settings_content)

        # Sub-views
        self.assertIn('id="settings-subview-testing-rag"', settings_content)
        self.assertIn('id="settings-subview-studio"', settings_content)
        self.assertIn('id="settings-subview-account"', settings_content)

        # RAG Playground must be under testing-rag subview
        testing_rag_subview_match = re.search(r'<div\s+id="settings-subview-testing-rag"[^>]*>(.*?)</div>\s*<!-- Subview 2', settings_content, re.DOTALL)
        self.assertIsNotNone(testing_rag_subview_match, "settings-subview-testing-rag must contain the playground.")
        self.assertIn('id="settings-rag-playground"', testing_rag_subview_match.group(1))

    def test_03_document_inspection_and_pdf_preview_modal(self):
        """Ensures document cross-verification modal and action buttons exist."""
        self.assertIn('id="document-inspect-modal"', self.html)
        self.assertIn('id="doc-modal-iframe"', self.html)
        self.assertIn('id="doc-modal-chunks-view"', self.html)
        self.assertIn('inspectDocument(', self.html)

    def test_04_deletion_controls_for_chat_and_tickets(self):
        """Ensures delete chat history and delete ticket action triggers exist."""
        self.assertIn('deleteChatSession(', self.html)
        self.assertIn('deleteTicket(', self.html)
        self.assertIn('/api/dashboard/chats/', self.html)
        self.assertIn('/api/tickets/', self.html)

if __name__ == "__main__":
    unittest.main()
