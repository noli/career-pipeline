import sys
import unittest
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

"""
tests/test_sanitization - Automated Security, Secret, and PII Leak Scanner
Validates that the repository contains zero hardcoded secrets, private keys,
internal LAN hostnames, personal machine paths, or untracked sensitive files.
Also executes local custom PII validation if .pii_patterns.local exists.
"""

# Generic leak patterns that must NEVER appear in tracked files
GENERIC_LEAK_PATTERNS = [
    (r"(?i)(?:BEGIN\s+(?:RSA|OPENSSH|EC|PGP|DSA)?\s*PRIVATE\s+KEY)", "Private cryptographic key"),
    (r"(?i)(?:ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36})", "GitHub personal token"),
    (r"(?i)sk-[a-zA-Z0-9]{32,}", "API secret key pattern (OpenAI/Anthropic)"),
    (r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\x22\x27][a-zA-Z0-9_\-]{20,}[\x22\x27]", "Hardcoded API key assignment"),
    (r"/Users/(?!username[\b/])[a-zA-Z0-9_.-]+/", "Hardcoded local macOS user home path"),
    (r"/home/(?!username[\b/])[a-zA-Z0-9_.-]+/", "Hardcoded local Linux user home path"),
    (r"C:[\\/]+Users[\\/]+(?!Username[\b\\/])[a-zA-Z0-9_.-]+[\\/]+", "Hardcoded local Windows user home path"),
]

ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "users.noreply.github.com",
    "github.com",
    "greenhouse.io",
    "lever.co",
    "personio.de",
    "ashbyhq.com",
    "smartrecruiters.com",
    "teamtailor.com",
    "recruitee.com",
    "myworkdayjobs.com",
    "serpapi.com"
}

class TestSanitization(unittest.TestCase):
    def test_zero_leaks_in_tracked_files(self):
        """Scans all tracked files for secrets, credentials, and forbidden path references."""
        scan_exts = {".py", ".yaml", ".yml", ".json", ".md", ".jinja", ".tex", ".sh", ".ps1", ".applescript", ".toml"}
        leaks = []

        # Load local custom PII patterns if present (.pii_patterns.local)
        local_patterns = []
        local_pii_file = REPO_ROOT / ".pii_patterns.local"
        if local_pii_file.exists():
            for line in local_pii_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    local_patterns.append(line)

        for path in REPO_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(p in path.parts for p in [".git", ".venv", "venv", "__pycache__", "data", "output"]):
                continue
            if path.suffix not in scan_exts:
                continue
            if path.name in ["test_sanitization.py", ".pii_patterns.local"]:
                continue

            content = path.read_text(encoding="utf-8", errors="ignore")

            # 1. Check generic leak patterns
            for pat, desc in GENERIC_LEAK_PATTERNS:
                matches = re.findall(pat, content)
                if matches:
                    rel = path.relative_to(REPO_ROOT)
                    leaks.append(f"[{desc}] in {rel}: matched {matches[0]!r}")

            # 2. Check email addresses
            for email in re.findall(r"[a-zA-Z0-9_.+-]+@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", content):
                domain = email.lower()
                if not any(domain == allowed or domain.endswith("." + allowed) for allowed in ALLOWED_EMAIL_DOMAINS):
                    rel = path.relative_to(REPO_ROOT)
                    leaks.append(f"[Unauthorized Email Domain] in {rel}: {email}")

            # 3. Check local PII patterns if available
            for pat in local_patterns:
                matches = re.findall(pat, content)
                if matches:
                    rel = path.relative_to(REPO_ROOT)
                    leaks.append(f"[Local PII Match] in {rel}: matched {matches[0]!r}")

        if leaks:
            self.fail(f"Found {len(leaks)} privacy/security leaks in repository:\n" + "\n".join(leaks))

    def test_sensitive_files_are_ignored(self):
        """Ensures .env and *.db are not tracked by git."""
        import subprocess
        tracked = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT).decode("utf-8").splitlines()
        for f in tracked:
            self.assertFalse(f.endswith(".db") or f.endswith(".sqlite"), f"Database file tracked in git: {f}")
            self.assertFalse(f == ".env" or f.endswith("/.env"), f".env file tracked in git: {f}")
            self.assertFalse(f.endswith(".eml") or f.endswith(".msg"), f"Email raw message tracked in git: {f}")
            self.assertFalse(f.endswith(".local"), f"Local secret file tracked in git: {f}")

if __name__ == "__main__":
    unittest.main()
