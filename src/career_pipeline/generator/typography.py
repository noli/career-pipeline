"""
career_pipeline.generator.typography - String Sanitization & Typography Rules
Cross-platform safe slugification and LaTeX character escaping.
"""
import re

WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10))
}

def slugify(text: str) -> str:
    """Converts string into a cross-platform (Windows & POSIX) safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    slug = text.strip("-.")
    if slug in WINDOWS_RESERVED_NAMES:
        slug = f"{slug}-role"
    return slug or "unnamed"

def latex_escape(text: str) -> str:
    """Escapes special LaTeX characters in dynamically interpolated strings."""
    if not text:
        return ""
    text = text.replace("\\", "\\textbackslash{}")
    text = text.replace("&", "\\&")
    text = text.replace("%", "\\%")
    text = text.replace("$", "\\$")
    text = text.replace("#", "\\#")
    text = text.replace("_", "\\_")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace("~", "\\textasciitilde{}")
    text = text.replace("^", "\\textasciicircum{}")
    text = text.replace("–", "--")
    text = text.replace("—", "---")
    text = text.replace("“", "``").replace("”", "''")
    return text
