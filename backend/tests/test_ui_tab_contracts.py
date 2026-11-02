import os
import re
import unittest

class TestUiTabContracts(unittest.TestCase):
    """Verifies that the single-page application UI maintains strict separation between views."""

    def setUp(self):
        html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "static", "index.html"))
        with open(html_path, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_01_top_nav_tabs_exist(self):
        """Ensures both Settings and RAG Playground exist as distinct tabs in the navigation bar."""
        self.assertIn('id="tab-settings"', self.html)
        self.assertIn('id="tab-playground"', self.html)
        self.assertIn('switchTab(\'settings\')', self.html)
        self.assertIn('switchTab(\'playground\')', self.html)

    def test_02_views_are_distinct_top_level_sections(self):
        """Ensures view-settings and view-playground are separate sections, not nested inside each other."""
        # Find the start and end of view-settings
        settings_match = re.search(r'<section\s+id="view-settings"[^>]*>(.*?)</section>', self.html, re.DOTALL)
        self.assertIsNotNone(settings_match, "view-settings section must exist and be closed properly.")
        settings_content = settings_match.group(1)

        # view-playground must NOT be inside view-settings
        self.assertNotIn('id="view-playground"', settings_content, "view-playground must not be nested inside view-settings.")

        # view-playground must exist as its own section
        playground_match = re.search(r'<section\s+id="view-playground"[^>]*>(.*?)</section>', self.html, re.DOTALL)
        self.assertIsNotNone(playground_match, "view-playground section must exist as an independent top-level section.")

    def test_03_switch_tab_direct_activation(self):
        """Ensures switchTab activates view-playground directly without redirecting to settings."""
        self.assertNotIn("switchTab('settings')", self.html[self.html.find("function switchTab"):self.html.find("function switchTab") + 500])

if __name__ == "__main__":
    unittest.main()
