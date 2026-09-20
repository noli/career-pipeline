import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
"""
tests/test_cross_platform - Windows, macOS, and Linux Compatibility Checks
"""
import unittest
from pathlib import Path
from career_pipeline.generator.typography import slugify, latex_escape, WINDOWS_RESERVED_NAMES
from career_pipeline.generator.tectonic import is_tectonic_installed

class TestCrossPlatform(unittest.TestCase):
    def test_windows_reserved_names_sanitization(self):
        """Ensures slugify avoids Windows reserved words like CON, PRN, NUL."""
        for res_name in ["con", "prn", "aux", "nul", "com1", "lpt1"]:
            slug = slugify(res_name)
            self.assertNotIn(slug, WINDOWS_RESERVED_NAMES)
            self.assertTrue(slug.endswith("-role"))

    def test_windows_forbidden_characters(self):
        r"""Ensures forbidden Windows characters (: * ? \" < > | \\ /) are stripped."""
        unsafe_title = 'Lead Architect: Senior/Principal *Perception* <LiDAR> "Alpha"?'
        slug = slugify(unsafe_title)
        for char in [":", "*", "?", '"', "<", ">", "|", "\\", "/"]:
            self.assertNotIn(char, slug)

    def test_latex_escape(self):
        """Verifies proper LaTeX typography and character escaping."""
        raw = "Robotics & AI (50% faster) #1 – Innovation"
        escaped = latex_escape(raw)
        self.assertIn(r"\&", escaped)
        self.assertIn(r"\%", escaped)
        self.assertIn(r"\#", escaped)
        self.assertIn("--", escaped)

    def test_tectonic_binary_check(self):
        """Verifies that tectonic check uses shutil.which without crashing."""
        installed = is_tectonic_installed()
        self.assertIsInstance(installed, bool)

if __name__ == "__main__":
    unittest.main()
