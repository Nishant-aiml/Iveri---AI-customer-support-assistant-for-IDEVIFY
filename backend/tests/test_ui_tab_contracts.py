import os
import re
import unittest

class TestUiTabContracts(unittest.TestCase):
    """Verifies that the single-page application UI maintains strict settings sub-tab hierarchy,

    interactive RAG testing on the right side of Account & Security, and no redundant playground in top navbar.
    """

    def setUp(self):
        html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "static", "index.html"))
        with open(html_path, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_01_top_nav_clean_and_no_navbar_playground(self):
        """Ensures Settings tab exists in top nav and RAG playground is removed from navbar."""
        self.assertIn('id="tab-settings"', self.html)
        self.assertNotIn('id="tab-playground"', self.html)
        self.assertIn('switchTab(\'settings\')', self.html)

    def test_02_settings_subtabs_order_and_testing_rag_on_right(self):
        """Ensures that under Settings, Testing RAG is positioned on the right side of Account & Security."""
        settings_match = re.search(r'<section\s+id="view-settings"[^>]*>(.*?)</section>', self.html, re.DOTALL)
        self.assertIsNotNone(settings_match, "view-settings section must exist.")
        settings_content = settings_match.group(1)

        # Sub-tab buttons exist
        self.assertIn('id="subtab-btn-studio"', settings_content)
        self.assertIn('id="subtab-btn-account"', settings_content)
        self.assertIn('id="subtab-btn-testing-rag"', settings_content)

        # Verify relative order: Studio before Account, and Account before Testing RAG (on right)
        idx_studio = settings_content.find('id="subtab-btn-studio"')
        idx_account = settings_content.find('id="subtab-btn-account"')
        idx_rag = settings_content.find('id="subtab-btn-testing-rag"')

        self.assertGreater(idx_account, idx_studio, "Account & Security must be after Widget Studio.")
        self.assertGreater(idx_rag, idx_account, "Testing RAG must be on the right side of Account & Security.")

        # Sub-views exist and Testing RAG contains the playground
        self.assertIn('id="settings-subview-testing-rag"', settings_content)
        self.assertIn('id="settings-rag-playground"', settings_content)

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

    def test_05_copilot_and_programmatic_playground_routing(self):
        """Ensures switchTab('playground') programmatically activates settings and selects testing-rag."""
        self.assertIn("tabId = 'settings';", self.html)
        self.assertIn("switchSettingsSubTab('testing-rag');", self.html)

if __name__ == "__main__":
    unittest.main()
