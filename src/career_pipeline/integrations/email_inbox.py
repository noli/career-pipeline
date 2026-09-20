#!/usr/bin/env python3
"""
Career/Scripts/email_parser.py - Parser for Incoming Job Alert Emails (.eml / .html)
Extracts positions from LinkedIn, StepStone, Indeed, and generic company job alerts.
Normalizes URLs, metadata, and timestamps for pipeline ingestion.
"""

import os
import re
import email
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from bs4 import BeautifulSoup

import hashlib

def compute_job_id(company: str = "", title: str = "", external_id: Optional[str] = None, url: Optional[str] = None, **kwargs) -> str:
    raw = f"{company.strip().lower()}:{title.strip().lower()}"
    if external_id:
        raw += f":{external_id}"
    elif url:
        raw += f":{url}"
    elif not raw or raw == ":":
        raw = kwargs.get("canonical_url", "")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def compute_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()



def parse_rfc2822_date(date_str: Optional[str]) -> str:
    """Parses email Date header into ISO-8601 UTC string."""
    if not date_str:
        return datetime.utcnow().isoformat() + "Z"
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone().isoformat()
    except Exception:
        return datetime.utcnow().isoformat() + "Z"


class EmailAlertParser:
    """Parses job alert emails into normalized job listings."""

    @classmethod
    def parse_eml_file(cls, eml_path: Path) -> List[Dict[str, Any]]:
        """Parses a .eml file and returns all detected job opportunities."""
        try:
            with open(eml_path, "rb") as f:
                msg = email.message_from_binary_file(f, policy=policy.default)
        except Exception as e:
            print(f"Error reading {eml_path}: {e}")
            return []

        subject = str(msg.get("subject", ""))
        sender = str(msg.get("from", ""))
        date_header = msg.get("date")
        posted_at_iso = parse_rfc2822_date(date_header)

        # Get HTML or plain text body
        html_body = ""
        plain_body = ""
        try:
            body_part = msg.get_body(preferencelist=("html", "plain"))
            if body_part:
                content = body_part.get_content()
                if body_part.get_content_type() == "text/html":
                    html_body = content
                else:
                    plain_body = content
        except Exception:
            pass

        # Fallback to walk parts if get_body was empty
        if not html_body and not plain_body:
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/html" and not html_body:
                    try:
                        html_body = part.get_content()
                    except Exception:
                        pass
                elif ctype == "text/plain" and not plain_body:
                    try:
                        plain_body = part.get_content()
                    except Exception:
                        pass

        results: List[Dict[str, Any]] = []

        if "linkedin" in sender.lower() or "linkedin" in subject.lower():
            results = cls.parse_linkedin_alert(html_body or plain_body, posted_at_iso, source_file=eml_path.name)
        elif "stepstone" in sender.lower() or "stepstone" in subject.lower():
            results = cls.parse_stepstone_alert(html_body or plain_body, posted_at_iso, source_file=eml_path.name)
        else:
            # Generic extractor
            results = cls.parse_generic_alert(html_body or plain_body, posted_at_iso, sender, subject, source_file=eml_path.name)

        return results

    @classmethod
    def parse_linkedin_alert(cls, content: str, posted_at_iso: str, source_file: str = "") -> List[Dict[str, Any]]:
        """Extracts job cards from LinkedIn Job Alert emails."""
        results = []
        soup = BeautifulSoup(content, "html.parser")
        now_iso = datetime.utcnow().isoformat() + "Z"
        seen_ids = set()

        # Find all links to jobs/view
        for a in soup.find_all("a", href=True):
            href = a["href"]
            match = re.search(r"jobs/view/(\d+)", href)
            if not match:
                continue

            job_id = match.group(1)
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            canonical_url = f"https://www.linkedin.com/jobs/view/{job_id}"

            # Extract card text from the link or parent table/container
            link_text = a.get_text(" ", strip=True)
            container = a.find_parent("tr") or a.find_parent("table") or a.parent
            container_text = container.get_text("\n", strip=True) if container else link_text

            lines = [l.strip() for l in container_text.splitlines() if l.strip()]

            # Determine title, company, location
            title = ""
            company = "Tech Employer"
            location = "Munich Area"

            # Typical LinkedIn layout:
            # Line 0: Job Title (e.g. "Optical Designer (f/m/d)")
            # Line 1: "QuantumDiamonds · Munich (On-site)" or separate lines
            if lines:
                title = lines[0]
                if len(lines) > 1:
                    info_line = lines[1]
                    if "·" in info_line:
                        parts = info_line.split("·")
                        company = parts[0].strip()
                        location = parts[1].strip()
                    elif " - " in info_line:
                        parts = info_line.split(" - ")
                        company = parts[0].strip()
                        location = parts[1].strip()
                    else:
                        company = info_line.strip()
                        if len(lines) > 2:
                            location = lines[2].strip()

            if not title or len(title) < 3 or "job alert" in title.lower() or "view job" in title.lower():
                # Fallback to link text
                if link_text and len(link_text) > 4:
                    title = link_text

            if not title:
                continue

            cid = compute_job_id(company, title, external_id=job_id, url=canonical_url)
            chash = compute_content_hash(f"{title} {company} {location} {canonical_url}")

            workplace_type = "remote" if "remote" in location.lower() or "remote" in title.lower() else "hybrid"
            if "on-site" in location.lower() or "vor ort" in location.lower():
                workplace_type = "onsite"

            results.append({
                "id": cid,
                "canonical_url": canonical_url,
                "company": company,
                "title": title,
                "location": location,
                "workplace_type": workplace_type,
                "department": "Engineering & Technology",
                "ats_source": "email_alert_linkedin",
                "raw_content": f"Source Email Alert: {source_file}\nTitle: {title}\nCompany: {company}\nLocation: {location}\nURL: {canonical_url}\n\nSnippet:\n{container_text[:2000]}",
                "content_hash": chash,
                "discovered_at": now_iso,
                "posted_at": posted_at_iso,
                "status": "new"
            })

        return results

    @classmethod
    def parse_stepstone_alert(cls, content: str, posted_at_iso: str, source_file: str = "") -> List[Dict[str, Any]]:
        """Extracts job cards from StepStone Job Agent emails."""
        results = []
        soup = BeautifulSoup(content, "html.parser")
        now_iso = datetime.utcnow().isoformat() + "Z"
        seen_urls = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "stepstone.de" not in href or ("stellenangebote" not in href and "/job/" not in href):
                continue

            # Strip tracking query params
            clean_url = href.split("?")[0]
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            text = a.get_text(" ", strip=True)
            if not text or len(text) < 4 or "mehr" in text.lower() or "jetzt bewerben" in text.lower():
                continue

            container = a.find_parent("tr") or a.find_parent("table") or a.parent
            container_text = container.get_text("\n", strip=True) if container else text

            lines = [l.strip() for l in container_text.splitlines() if l.strip()]
            title = text
            company = "Tech Employer"
            location = "Munich Area"

            if len(lines) >= 2:
                title = lines[0]
                company = lines[1]
                if len(lines) >= 3:
                    location = lines[2]

            cid = compute_job_id(company, title, url=clean_url)
            chash = compute_content_hash(f"{title} {company} {clean_url}")

            results.append({
                "id": cid,
                "canonical_url": clean_url,
                "company": company,
                "title": title,
                "location": location,
                "workplace_type": "hybrid",
                "department": "Engineering & Technology",
                "ats_source": "email_alert_stepstone",
                "raw_content": f"Source Email Alert: {source_file}\nTitle: {title}\nCompany: {company}\nLocation: {location}\nURL: {clean_url}\n\nSnippet:\n{container_text[:2000]}",
                "content_hash": chash,
                "discovered_at": now_iso,
                "posted_at": posted_at_iso,
                "status": "new"
            })

        return results

    @classmethod
    def parse_generic_alert(cls, content: str, posted_at_iso: str, sender: str, subject: str, source_file: str = "") -> List[Dict[str, Any]]:
        """Fallback extractor for generic employer alerts, Indeed, or Xing."""
        results = []
        soup = BeautifulSoup(content, "html.parser")
        now_iso = datetime.utcnow().isoformat() + "Z"
        seen_urls = set()

        job_keywords = ["engineer", "director", "lead", "head", "architect", "physiker", "scientist", "consultant", "manager"]

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)

            # Check if text contains a relevant job title
            is_job = any(k in text.lower() for k in job_keywords) and len(text) > 8
            if not is_job:
                continue

            clean_url = href.split("?")[0]
            if clean_url in seen_urls or clean_url.startswith("mailto:"):
                continue
            seen_urls.add(clean_url)

            company = sender.split("<")[0].replace('"', "").strip() or "Employer"
            title = text

            cid = compute_job_id(company, title, url=clean_url)
            chash = compute_content_hash(f"{title} {company} {clean_url}")

            results.append({
                "id": cid,
                "canonical_url": clean_url,
                "company": company,
                "title": title,
                "location": "Munich Area / Flexible",
                "workplace_type": "hybrid",
                "department": "Engineering & Technology",
                "ats_source": "email_alert_generic",
                "raw_content": f"Source Email Alert: {source_file}\nSender: {sender}\nSubject: {subject}\nTitle: {title}\nURL: {clean_url}",
                "content_hash": chash,
                "discovered_at": now_iso,
                "posted_at": posted_at_iso,
                "status": "new"
            })

        return results


def process_inbox_directory(inbox_dir: Path, archive_dir: Path) -> List[Dict[str, Any]]:
    """Scans inbox_dir for .eml files, extracts positions, and archives processed files."""
    all_jobs: List[Dict[str, Any]] = []
    eml_files = sorted(list(inbox_dir.glob("*.eml")) + list(inbox_dir.glob("*.msg")))

    if not eml_files:
        return []

    for fpath in eml_files:
        jobs = EmailAlertParser.parse_eml_file(fpath)
        all_jobs.extend(jobs)
        # Archive file with timestamp prefix
        archive_name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{fpath.name}"
        dest = archive_dir / archive_name
        try:
            fpath.rename(dest)
        except Exception:
            pass

    return all_jobs
