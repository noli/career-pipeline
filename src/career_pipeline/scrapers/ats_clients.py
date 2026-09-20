#!/usr/bin/env python3
"""
Career/Scripts/ats_clients.py - Connectors for Public ATS Boards & Job Feeds
Supports Greenhouse, Lever, Personio XML, and generic web extraction.
"""

import os
import re
import html
import requests
import xml.etree.ElementTree as ET
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


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, application/xml, text/html, */*"
}


def clean_html_text(raw_html: str) -> str:
    """Strips HTML tags and unescapes entities to yield clean plain text."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(html.unescape(raw_html), "html.parser")
    text = soup.get_text(separator="\n")
    # Normalize excessive newlines
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text


class GreenhouseClient:
    """Fetches jobs from public Greenhouse API boards."""

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"

    @classmethod
    def fetch_jobs(cls, board_token: str, company_name: str, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        url = cls.BASE_URL.format(board=board_token)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                print(f"Greenhouse [{board_token}]: HTTP {resp.status_code}")
                return []
            data = resp.json()
            jobs = data.get("jobs", [])
        except Exception as e:
            print(f"Greenhouse [{board_token}] error: {e}")
            return []

        results = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        for j in jobs:
            job_id = str(j.get("id", ""))
            title = j.get("title", "").strip()
            loc = j.get("location", {}).get("name", "")
            departments = [d.get("name") for d in j.get("departments", []) if d.get("name")]
            dept = ", ".join(departments)
            job_url = j.get("absolute_url", "")
            raw_content = clean_html_text(j.get("content", ""))

            # Location filtering
            if location_filter:
                match_loc = any(lf.lower() in loc.lower() or lf.lower() in title.lower() for lf in location_filter)
                if not match_loc and loc:
                    continue

            workplace_type = "remote" if "remote" in loc.lower() or "remote" in title.lower() else "hybrid"
            content_hash = compute_content_hash(f"{title} {loc} {raw_content}")

            results.append({
                "id": compute_job_id(company_name, title, external_id=job_id),
                "canonical_url": job_url,
                "company": company_name,
                "title": title,
                "location": loc or "Munich Area",
                "workplace_type": workplace_type,
                "department": dept,
                "ats_source": "greenhouse",
                "raw_content": raw_content,
                "content_hash": content_hash,
                "discovered_at": now_iso,
                "posted_at": j.get("updated_at", now_iso),
                "status": "new"
            })
        return results


class LeverClient:
    """Fetches jobs from public Lever API boards (supports US and EU data residency endpoints)."""

    BASE_URL = "https://api.lever.co/v0/postings/{company}?mode=json"
    EU_BASE_URL = "https://api.eu.lever.co/v0/postings/{company}?mode=json"

    @classmethod
    def fetch_jobs(cls, company_slug: str, company_name: str, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        postings = []
        for url in [cls.BASE_URL.format(company=company_slug), cls.EU_BASE_URL.format(company=company_slug)]:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                if resp.status_code == 200:
                    postings = resp.json()
                    break
                elif resp.status_code != 404:
                    print(f"Lever [{company_slug}] {url}: HTTP {resp.status_code}")
            except Exception as e:
                print(f"Lever [{company_slug}] {url} error: {e}")

        if not postings:
            return []

        results = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        for p in postings:
            job_id = str(p.get("id", ""))
            title = p.get("text", "").strip()
            cats = p.get("categories", {})
            loc = cats.get("location", "")
            dept = cats.get("department", "") or cats.get("team", "")
            workplace_type = cats.get("workplaceType", "hybrid")
            job_url = p.get("hostedUrl", "")
            raw_content = clean_html_text(p.get("descriptionPlain", "") or p.get("description", ""))

            if location_filter:
                match_loc = any(lf.lower() in loc.lower() or lf.lower() in title.lower() for lf in location_filter)
                if not match_loc and loc:
                    continue

            content_hash = compute_content_hash(f"{title} {loc} {raw_content}")

            results.append({
                "id": compute_job_id(company_name, title, external_id=job_id),
                "canonical_url": job_url,
                "company": company_name,
                "title": title,
                "location": loc or "Munich Area",
                "workplace_type": workplace_type,
                "department": dept,
                "ats_source": "lever",
                "raw_content": raw_content,
                "content_hash": content_hash,
                "discovered_at": now_iso,
                "posted_at": datetime.fromtimestamp(p.get("createdAt", 0)/1000.0).isoformat() + "Z" if p.get("createdAt") else now_iso,
                "status": "new"
            })
        return results


class PersonioClient:
    """Fetches jobs from Personio XML feeds."""

    BASE_URL = "https://{company}.jobs.personio.de/xml"

    @classmethod
    def fetch_jobs(cls, company_slug: str, company_name: str, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        url = cls.BASE_URL.format(company=company_slug)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                print(f"Personio [{company_slug}]: HTTP {resp.status_code}")
                return []
            if not resp.content.strip().startswith(b"<?xml") and not resp.content.strip().startswith(b"<workzag"):
                # Not valid XML (e.g. Cloudflare challenge page)
                return []
            root = ET.fromstring(resp.content)
        except Exception:
            return []

        results = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        for pos in root.findall(".//position") or root.findall(".//job"):
            job_id = pos.findtext("id") or ""
            title = (pos.findtext("name") or pos.findtext("title") or "").strip()
            loc = pos.findtext("office") or pos.findtext("location") or ""
            dept = pos.findtext("department") or ""
            
            # Extract keywords and metadata
            keywords = (pos.findtext("keywords") or "").strip()
            occupation = (pos.findtext("occupation") or "").strip()
            seniority_meta = (pos.findtext("seniority") or "").strip()

            # Combine job descriptions
            desc_parts = []
            for d in pos.findall(".//jobDescription"):
                name = d.findtext("name") or ""
                val = d.findtext("value") or ""
                desc_parts.append(f"### {name}\n{clean_html_text(val)}")
            raw_content = "\n\n".join(desc_parts)

            # If XML has no text body, fetch from the job page
            if len(raw_content) < 100:
                try:
                    job_page_resp = requests.get(job_url, headers=HEADERS, timeout=8)
                    if job_page_resp.status_code == 200:
                        soup = BeautifulSoup(job_page_resp.content, "html.parser")
                        for s in soup(["script", "style", "nav", "header", "footer"]):
                            s.decompose()
                        raw_content = soup.get_text(separator="\n").strip()
                except Exception:
                    pass

            # Augment with metadata
            meta_str = f"Keywords: {keywords}\nOccupation: {occupation}\nDepartment: {dept}\nSeniority: {seniority_meta}"
            raw_content = f"{meta_str}\n\n{raw_content}".strip()

            if location_filter:
                match_loc = any(lf.lower() in loc.lower() or lf.lower() in title.lower() for lf in location_filter)
                if not match_loc and loc:
                    continue

            job_url = f"https://{company_slug}.jobs.personio.de/job/{job_id}"
            content_hash = compute_content_hash(f"{title} {loc} {raw_content}")

            created_at_meta = pos.findtext("createdAt") or pos.findtext("created-at") or now_iso

            results.append({
                "id": compute_job_id(company_name, title, external_id=job_id),
                "canonical_url": job_url,
                "company": company_name,
                "title": title,
                "location": loc or "Munich Area",
                "workplace_type": "hybrid",
                "department": dept,
                "ats_source": "personio",
                "raw_content": raw_content,
                "content_hash": content_hash,
                "discovered_at": now_iso,
                "posted_at": created_at_meta,
                "status": "new"
            })
        return results


class TeamtailorClient:
    """Fetches jobs from public Teamtailor feeds (e.g. IQM Quantum Computers)."""

    BASE_URL = "https://{company}.teamtailor.com/jobs.json"

    @classmethod
    def fetch_jobs(cls, company_slug: str, company_name: str, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        url = cls.BASE_URL.format(company=company_slug)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                print(f"Teamtailor [{company_slug}]: HTTP {resp.status_code}")
                return []
            data = resp.json()
            items = data.get("items", [])
        except Exception as e:
            print(f"Teamtailor [{company_slug}] error: {e}")
            return []

        results = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        for item in items:
            title = (item.get("title") or "").strip()
            job_url = item.get("url", "")
            raw_html = item.get("content_html", "")
            loc = (item.get("location") or "Munich / Espoo / Hybrid").strip()
            
            # Extract plain text
            raw_content = clean_html_text(raw_html)
            
            # If location is empty or generic, check content
            if location_filter:
                match_loc = any(lf.lower() in loc.lower() or lf.lower() in title.lower() or lf.lower() in raw_content[:500].lower() for lf in location_filter)
                if not match_loc and loc:
                    continue

            job_id = compute_job_id(company_name, title, url=job_url)
            content_hash = compute_content_hash(f"{title} {loc} {raw_content}")

            results.append({
                "id": job_id,
                "canonical_url": job_url,
                "company": company_name,
                "title": title,
                "location": loc or "Munich Area",
                "workplace_type": "hybrid",
                "department": "Quantum Hardware / Engineering",
                "ats_source": "teamtailor",
                "raw_content": raw_content,
                "content_hash": content_hash,
                "discovered_at": now_iso,
                "posted_at": item.get("date_published", now_iso),
                "status": "new"
            })
        return results


class MQVClient:
    """Scrapes the Munich Quantum Valley job board for research and industry openings."""

    BASE_URL = "https://www.munich-quantum-valley.de/service/jobs"

    @classmethod
    def fetch_jobs(cls) -> List[Dict[str, Any]]:
        try:
            resp = requests.get(cls.BASE_URL, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.content, "html.parser")
        except Exception as e:
            print(f"MQV scrape error: {e}")
            return []

        results = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/service/job/" in href or "/job/" in href:
                full_url = "https://www.munich-quantum-valley.de" + href if href.startswith("/") else href
                title = a.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                
                # Fetch full job text
                try:
                    jresp = requests.get(full_url, headers=HEADERS, timeout=8)
                    if jresp.status_code == 200:
                        jsoup = BeautifulSoup(jresp.content, "html.parser")
                        for s in jsoup(["script", "style", "nav", "header", "footer"]):
                            s.decompose()
                        content = jsoup.get_text(separator="\n").strip()
                    else:
                        content = title
                except Exception:
                    content = title

                job_id = compute_job_id("Munich Quantum Valley", title, url=full_url)
                chash = compute_content_hash(f"{title} {content[:2000]}")

                results.append({
                    "id": job_id,
                    "canonical_url": full_url,
                    "company": "Munich Quantum Valley",
                    "title": title,
                    "location": "Garching / Munich, Germany",
                    "workplace_type": "hybrid",
                    "department": "Quantum Systems & Hardware",
                    "ats_source": "mqv_board",
                    "raw_content": content,
                    "content_hash": chash,
                    "discovered_at": now_iso,
                    "posted_at": now_iso,
                    "status": "new"
                })
        return results


class RecruiteeClient:
    """Fetches jobs from Recruitee public APIs (e.g. Quantum-Systems / Fernride)."""

    @classmethod
    def fetch_jobs(cls, board_id_or_url: str, company_name: str, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if board_id_or_url.startswith("http"):
            url = board_id_or_url
        else:
            url = f"https://{board_id_or_url}.recruitee.com/api/offers/"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                print(f"Recruitee [{board_id_or_url}]: HTTP {resp.status_code}")
                return []
            data = resp.json()
            offers = data.get("offers", [])
        except Exception as e:
            print(f"Recruitee [{board_id_or_url}] error: {e}")
            return []

        results = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        for o in offers:
            title = (o.get("title") or "").strip()
            city = (o.get("city") or "").strip()
            state = (o.get("state_name") or o.get("state_code") or "").strip()
            country = (o.get("country") or "").strip()
            loc_parts = [p for p in [city, state, country] if p]
            location = ", ".join(loc_parts) or "Munich Area"
            
            job_url = o.get("careers_url") or f"https://career.quantum-systems.com/o/{o.get('slug', '')}"
            dept = o.get("department") or "Engineering"
            desc_html = o.get("description") or ""
            req_html = o.get("requirements") or ""
            raw_content = clean_html_text(f"{desc_html}\n\nRequirements:\n{req_html}")

            is_remote = bool(o.get("remote", False))
            is_hybrid = bool(o.get("hybrid", False))
            workplace_type = "remote" if is_remote else ("hybrid" if is_hybrid else "onsite")

            # Location filtering
            if location_filter:
                match_loc = any(lf.lower() in location.lower() or lf.lower() in title.lower() or (is_remote and "remote" in lf.lower()) for lf in location_filter)
                if not match_loc and location:
                    continue

            job_id = compute_job_id(company_name, title, url=job_url)
            chash = compute_content_hash(f"{title} {location} {raw_content[:2000]}")

            results.append({
                "id": job_id,
                "canonical_url": job_url,
                "company": company_name,
                "title": title,
                "location": location,
                "workplace_type": workplace_type,
                "department": dept,
                "ats_source": "recruitee",
                "raw_content": raw_content,
                "content_hash": chash,
                "discovered_at": now_iso,
                "posted_at": o.get("published_at") or now_iso,
                "status": "new"
            })
        return results


class AshbyClient:
    """Fetches jobs from Ashby public APIs (e.g. The Exploration Company, Proxima Fusion)."""

    BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{board}"

    @classmethod
    def fetch_jobs(cls, board_token: str, company_name: str, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        url = cls.BASE_URL.format(board=board_token)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                print(f"Ashby [{board_token}]: HTTP {resp.status_code}")
                return []
            data = resp.json()
            jobs = data.get("jobs", [])
        except Exception as e:
            print(f"Ashby [{board_token}] error: {e}")
            return []

        results = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        for j in jobs:
            title = (j.get("title") or "").strip()
            loc = (j.get("location") or "").strip()
            dept = (j.get("department") or "Engineering").strip()
            job_url = j.get("jobUrl", "")
            raw_content = j.get("descriptionPlain") or clean_html_text(j.get("descriptionHtml", ""))
            
            is_remote = bool(j.get("isRemote", False))
            workplace_type = "remote" if is_remote else (j.get("workplaceType") or "hybrid")

            if location_filter:
                match_loc = any(lf.lower() in loc.lower() or lf.lower() in title.lower() or (is_remote and "remote" in lf.lower()) for lf in location_filter)
                if not match_loc and loc:
                    continue

            job_id = compute_job_id(company_name, title, url=job_url)
            chash = compute_content_hash(f"{title} {loc} {raw_content[:2000]}")

            results.append({
                "id": job_id,
                "canonical_url": job_url,
                "company": company_name,
                "title": title,
                "location": loc or "Munich, Germany",
                "workplace_type": workplace_type,
                "department": dept,
                "ats_source": "ashby",
                "raw_content": raw_content,
                "content_hash": chash,
                "discovered_at": now_iso,
                "posted_at": j.get("publishedAt") or now_iso,
                "status": "new"
            })
        return results


class TopticaClient:
    """Scrapes TOPTICA Photonics career listings and detail pages."""

    LIST_URL = "https://careers.toptica.com/prj/lst/a181a603769c1f98ad927e7367c7aa51/GesamtlisteOffenePositionen.htm"

    @classmethod
    def fetch_jobs(cls, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        try:
            resp = requests.get(cls.LIST_URL, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                print(f"TOPTICA: HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.content, "html.parser")
        except Exception as e:
            print(f"TOPTICA list error: {e}")
            return []

        results = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        for el in soup.find_all(attrs={"onclick": True}):
            onclick = el["onclick"]
            m = re.search(r"cJobboard\.openJob\('([^']+)'\)", onclick)
            if not m:
                continue
            job_url = m.group(1)
            title = el.get_text(strip=True)
            if not title or len(title) < 4:
                continue

            try:
                jresp = requests.get(job_url, headers=HEADERS, timeout=8)
                if jresp.status_code == 200:
                    jsoup = BeautifulSoup(jresp.content, "html.parser")
                    for s in jsoup(["script", "style", "nav", "header", "footer"]):
                        s.decompose()
                    content = jsoup.get_text(separator="\n").strip()
                    content = re.sub(r"\n\s*\n+", "\n\n", content)
                else:
                    content = title
            except Exception:
                content = title

            loc = "Gräfelfing / Munich, Germany"
            job_id = compute_job_id("TOPTICA Photonics", title, url=job_url)
            chash = compute_content_hash(f"{title} {loc} {content[:2000]}")

            results.append({
                "id": job_id,
                "canonical_url": job_url,
                "company": "TOPTICA Photonics",
                "title": title,
                "location": loc,
                "workplace_type": "hybrid",
                "department": "Optics & Laser Systems R&D",
                "ats_source": "toptica_board",
                "raw_content": content,
                "content_hash": chash,
                "discovered_at": now_iso,
                "posted_at": now_iso,
                "status": "new"
            })
        return results


class SmartRecruitersClient:
    """Fetches jobs from SmartRecruiters public API (e.g. Roland Berger)."""

    BASE_URL = "https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100"

    @classmethod
    def fetch_jobs(cls, company_id: str, company_name: str, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        url = cls.BASE_URL.format(company=company_id)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                print(f"SmartRecruiters [{company_id}]: HTTP {resp.status_code}")
                return []
            data = resp.json()
            postings = data.get("content", [])
        except Exception as e:
            print(f"SmartRecruiters [{company_id}] error: {e}")
            return []

        results = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        for p in postings:
            title = (p.get("name") or "").strip()
            loc_data = p.get("location", {})
            city = (loc_data.get("city") or "").strip()
            country = (loc_data.get("country") or "").strip()
            location = f"{city}, {country}".strip(", ")
            dept = p.get("department", {}).get("label") or "Consulting"
            posting_id = p.get("id")
            job_url = f"https://jobs.smartrecruiters.com/{company_id}/{posting_id}"

            if location_filter:
                match_loc = any(lf.lower() in location.lower() or lf.lower() in title.lower() for lf in location_filter)
                if not match_loc and location:
                    continue

            # Fetch detailed posting to get job description & qualifications
            try:
                det_resp = requests.get(f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings/{posting_id}", headers=HEADERS, timeout=8)
                if det_resp.status_code == 200:
                    det = det_resp.json()
                    sections = det.get("jobAd", {}).get("sections", {})
                    sec_texts = []
                    for s in sections.values():
                        title_s = s.get("title", "")
                        body_s = clean_html_text(s.get("text", ""))
                        if body_s:
                            sec_texts.append(f"{title_s}:\n{body_s}" if title_s else body_s)
                    raw_content = "\n\n".join(sec_texts)
                else:
                    raw_content = title
            except Exception:
                raw_content = title

            job_id = compute_job_id(company_name, title, url=job_url)
            chash = compute_content_hash(f"{title} {location} {raw_content[:2000]}")

            results.append({
                "id": job_id,
                "canonical_url": job_url,
                "company": company_name,
                "title": title,
                "location": location or "Munich, Germany",
                "workplace_type": "hybrid",
                "department": dept,
                "ats_source": "smartrecruiters",
                "raw_content": raw_content,
                "content_hash": chash,
                "discovered_at": now_iso,
                "posted_at": p.get("releasedDate") or now_iso,
                "status": "new"
            })
        return results


class WorkdayClient:
    """Fetches jobs from public Workday Career site REST endpoints (e.g. DELO, EOS)."""

    @classmethod
    def fetch_jobs(cls, config: Any, company_name: str, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if isinstance(config, dict):
            host = config.get("host", "")
            tenant = config.get("tenant", "")
            site = config.get("site", "")
        else:
            print(f"Workday [{company_name}]: Invalid config format")
            return []

        list_url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        now_iso = datetime.utcnow().isoformat() + "Z"
        results = []

        search_terms = config.get("search_terms") or [""]
        seen_paths = set()

        for term in search_terms:
            offset = 0
            limit = 20
            total = None

            while True:
                payload = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": term}
                try:
                    resp = requests.post(
                        list_url,
                        json=payload,
                        headers={"User-Agent": HEADERS["User-Agent"], "Content-Type": "application/json"},
                        timeout=12
                    )
                    if resp.status_code != 200:
                        print(f"Workday [{company_name}] (term '{term}'): HTTP {resp.status_code}")
                        break
                    data = resp.json()
                    if total is None:
                        total = data.get("total", 0)

                    postings = data.get("jobPostings", [])
                    if not postings:
                        break

                    for p in postings:
                        ext_path = p.get("externalPath", "")
                        if ext_path in seen_paths:
                            continue
                        seen_paths.add(ext_path)

                        title = (p.get("title") or "").strip()
                        loc = (p.get("locationsText") or "").strip()
                        job_url = f"https://{host}/en-US/{site}{ext_path}"

                        if location_filter:
                            match_loc = any(lf.lower() in loc.lower() or lf.lower() in title.lower() for lf in location_filter)
                            if not match_loc and loc:
                                continue

                        posted_date = now_iso
                        # Fetch detail for full description
                        raw_content = title
                        try:
                            detail_url = f"https://{host}/wday/cxs/{tenant}/{site}{ext_path}"
                            d_resp = requests.get(detail_url, headers=HEADERS, timeout=8)
                            if d_resp.status_code == 200:
                                d_info = d_resp.json().get("jobPostingInfo", {})
                                desc_html = d_info.get("jobDescription", "")
                                if desc_html:
                                    raw_content = clean_html_text(desc_html)
                                start_date = d_info.get("startDate")
                                if start_date:
                                    posted_date = f"{start_date}T00:00:00Z"
                        except Exception:
                            pass

                        job_id = compute_job_id(company_name, title, url=job_url)
                        chash = compute_content_hash(f"{title} {loc} {raw_content[:2000]}")

                        results.append({
                            "id": job_id,
                            "canonical_url": job_url,
                            "company": company_name,
                            "title": title,
                            "location": loc or "Munich Area",
                            "workplace_type": "hybrid",
                            "department": "Engineering & Technology",
                            "ats_source": "workday",
                            "raw_content": raw_content,
                            "content_hash": chash,
                            "discovered_at": now_iso,
                            "posted_at": posted_date,
                            "status": "new"
                        })

                    offset += limit
                    if offset >= total or offset >= 100:
                        break
                except Exception as e:
                    print(f"Workday [{company_name}] (term '{term}') error: {e}")
                    break

        return results


class SuccessFactorsClient:
    """Fetches jobs from SAP SuccessFactors Career Site Builder portals (e.g. Hensoldt, Knorr-Bremse)."""

    @classmethod
    def fetch_jobs(cls, config: Any, company_name: str, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        base_url = config.get("base_url", "").rstrip("/") if isinstance(config, dict) else ""
        search_terms = config.get("search_terms") or ["München", "Munich"] if isinstance(config, dict) else ["München"]
        max_pages = config.get("max_pages", 2) if isinstance(config, dict) else 2
        if not base_url:
            return []

        now_iso = datetime.utcnow().isoformat() + "Z"
        results = []
        seen_urls = set()

        for term in search_terms:
            for page in range(max_pages):
                startrow = page * 25
                search_url = f"{base_url}/search/?createNewAlert=false&q=&locationsearch={term}&startrow={startrow}"
                try:
                    resp = requests.get(search_url, headers=HEADERS, timeout=10)
                    if resp.status_code != 200:
                        break
                    soup = BeautifulSoup(resp.text, "html.parser")
                    job_links = []
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/job/" in href and a.text.strip():
                            full_url = href if href.startswith("http") else base_url + href
                            title = a.text.strip()
                            job_links.append((title, full_url))

                    if not job_links:
                        break

                    for title, job_url in job_links:
                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        loc = term
                        if location_filter:
                            match_loc = any(lf.lower() in loc.lower() or lf.lower() in title.lower() for lf in location_filter)
                            if not match_loc and loc:
                                continue

                        raw_content = title
                        posted_date = now_iso
                        try:
                            d_resp = requests.get(job_url, headers=HEADERS, timeout=8)
                            if d_resp.status_code == 200:
                                d_soup = BeautifulSoup(d_resp.text, "html.parser")
                                d_elem = d_soup.find("div", class_="job-description") or d_soup.find("span", class_="jobdescription") or d_soup.find("div", class_="job")
                                if d_elem:
                                    raw_content = clean_html_text(d_elem.get_text("\n"))
                                for s in d_soup.find_all("script", type="application/ld+json"):
                                    try:
                                        sdata = json.loads(s.string or "{}")
                                        if isinstance(sdata, list):
                                            sdata = next((x for x in sdata if x.get("@type") == "JobPosting"), {})
                                        if sdata.get("@type") == "JobPosting":
                                            dp = sdata.get("datePosted")
                                            if dp:
                                                posted_date = f"{dp}T00:00:00Z" if len(dp) == 10 else dp
                                            loc_val = sdata.get("jobLocation", {}).get("address", {}).get("addressLocality") or sdata.get("jobLocation", {}).get("address", {}).get("addressRegion")
                                            if loc_val:
                                                loc = loc_val
                                    except Exception:
                                        pass
                        except Exception:
                            pass

                        job_id = compute_job_id(company_name, title, url=job_url)
                        chash = compute_content_hash(f"{title} {loc} {raw_content[:2000]}")
                        results.append({
                            "id": job_id,
                            "canonical_url": job_url,
                            "company": company_name,
                            "title": title,
                            "location": loc or "Munich Area",
                            "workplace_type": "hybrid",
                            "department": "Engineering & Technology",
                            "ats_source": "successfactors",
                            "raw_content": raw_content,
                            "content_hash": chash,
                            "discovered_at": now_iso,
                            "posted_at": posted_date,
                            "status": "new"
                        })
                except Exception as e:
                    print(f"SuccessFactors [{company_name}] error: {e}")
                    break

        return results


class AvatureClient:
    """Fetches jobs from Avature career sites (e.g. Rohde & Schwarz, Siemens)."""

    @classmethod
    def fetch_jobs(cls, config: Any, company_name: str, location_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        base_url = config.get("base_url", "").rstrip("/") if isinstance(config, dict) else ""
        search_terms = config.get("search_terms") or ["Munich", "München"] if isinstance(config, dict) else ["Munich"]
        if not base_url:
            return []

        now_iso = datetime.utcnow().isoformat() + "Z"
        results = []
        seen_urls = set()

        for term in search_terms:
            for offset in [0, 10]:
                search_url = f"{base_url}/SearchJobs/{term}?jobRecordsPerPage=10&jobOffset={offset}"
                try:
                    resp = requests.get(search_url, headers=HEADERS, timeout=10)
                    if resp.status_code != 200:
                        break
                    soup = BeautifulSoup(resp.text, "html.parser")
                    job_links = []
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        title = a.text.strip()
                        if "/JobDetail/" in href and title and title.lower() not in ["apply", "learn more"]:
                            full_url = href if href.startswith("http") else base_url + href
                            job_links.append((title, full_url))

                    if not job_links:
                        break

                    for title, job_url in job_links:
                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        loc = term
                        if location_filter:
                            match_loc = any(lf.lower() in loc.lower() or lf.lower() in title.lower() for lf in location_filter)
                            if not match_loc and loc:
                                continue

                        raw_content = title
                        posted_date = now_iso
                        try:
                            d_resp = requests.get(job_url, headers=HEADERS, timeout=8)
                            if d_resp.status_code == 200:
                                d_soup = BeautifulSoup(d_resp.text, "html.parser")
                                for s in d_soup.find_all("script", type="application/ld+json"):
                                    try:
                                        sdata = json.loads(s.string or "{}")
                                        if isinstance(sdata, list):
                                            sdata = next((x for x in sdata if x.get("@type") == "JobPosting"), {})
                                        if sdata.get("@type") == "JobPosting":
                                            dp = sdata.get("datePosted")
                                            if dp:
                                                posted_date = f"{dp}T00:00:00Z" if len(dp) == 10 else dp
                                            loc_val = sdata.get("jobLocation", {}).get("address", {}).get("addressLocality")
                                            if loc_val:
                                                loc = loc_val
                                            desc = sdata.get("description")
                                            if desc:
                                                raw_content = clean_html_text(desc)
                                    except Exception:
                                        pass
                                if raw_content == title:
                                    body_text = d_soup.get_text("\n")
                                    raw_content = clean_html_text(body_text)
                        except Exception:
                            pass

                        job_id = compute_job_id(company_name, title, url=job_url)
                        chash = compute_content_hash(f"{title} {loc} {raw_content[:2000]}")
                        results.append({
                            "id": job_id,
                            "canonical_url": job_url,
                            "company": company_name,
                            "title": title,
                            "location": loc or "Munich",
                            "workplace_type": "hybrid",
                            "department": "Engineering & Technology",
                            "ats_source": "avature",
                            "raw_content": raw_content,
                            "content_hash": chash,
                            "discovered_at": now_iso,
                            "posted_at": posted_date,
                            "status": "new"
                        })
                except Exception as e:
                    print(f"Avature [{company_name}] error: {e}")
                    break

        return results


class MTUClient:
    """Fetches jobs from MTU Aero Engines Munich career site using listing cards & Schema.org JSON-LD."""

    @classmethod
    def fetch_jobs(cls, location_filter: Optional[List[str]] = None, company_name: str = "MTU Aero Engines") -> List[Dict[str, Any]]:
        list_url = "https://www.mtu.de/de/karriere/jobboerse/"
        now_iso = datetime.utcnow().isoformat() + "Z"
        results = []
        seen_urls = set()

        try:
            resp = requests.get(list_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")

            candidate_cards = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/stellenanzeige/" in href:
                    full_url = href if href.startswith("http") else "https://www.mtu.de" + href
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)

                    parent = a.find_parent("div")
                    p_text = parent.get_text("\n") if parent else ""
                    lines = [l.strip() for l in p_text.splitlines() if l.strip()]
                    title = lines[0] if lines else a.text.strip()
                    loc = "München" if "München" in p_text or "Munich" in p_text else "Germany"

                    if location_filter:
                        match_loc = any(lf.lower() in loc.lower() or lf.lower() in title.lower() for lf in location_filter)
                        if not match_loc:
                            continue

                    candidate_cards.append((title, full_url, loc))

            # Fetch detailed job descriptions for top 20 candidate jobs
            for title, job_url, loc in candidate_cards[:20]:
                raw_content = title
                posted_date = now_iso
                try:
                    d_resp = requests.get(job_url, headers=HEADERS, timeout=6)
                    if d_resp.status_code == 200:
                        d_soup = BeautifulSoup(d_resp.text, "html.parser")
                        for s in d_soup.find_all("script", type="application/ld+json"):
                            try:
                                txt = s.get_text() or ""
                                data = json.loads(txt)
                                if isinstance(data, list):
                                    data = next((x for x in data if x.get("@type") == "JobPosting"), {})
                                if data.get("@type") == "JobPosting":
                                    dp = data.get("datePosted")
                                    if dp:
                                        posted_date = f"{dp}T00:00:00Z" if len(dp) == 10 else dp
                                    raw_desc = data.get("description", "")
                                    if raw_desc:
                                        raw_content = clean_html_text(raw_desc)
                                    break
                            except Exception:
                                pass
                except Exception:
                    pass

                job_id = compute_job_id(company_name, title, url=job_url)
                chash = compute_content_hash(f"{title} {loc} {raw_content[:2000]}")
                results.append({
                    "id": job_id,
                    "canonical_url": job_url,
                    "company": company_name,
                    "title": title,
                    "location": loc,
                    "workplace_type": "hybrid",
                    "department": "Aviation & Engineering",
                    "ats_source": "mtu",
                    "raw_content": raw_content,
                    "content_hash": chash,
                    "discovered_at": now_iso,
                    "posted_at": posted_date,
                    "status": "new"
                })

        except Exception as e:
            print(f"MTUClient error: {e}")

        return results


def fetch_arbitrary_url(url: str, company: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetches and parses a single job posting from an arbitrary URL (with Apple Careers hydration)."""
    import json
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            print(f"Failed to fetch URL {url}: HTTP {resp.status_code}")
            return None

        comp = company or "Target Company"
        title = "Imported Job Posting"
        location = "Munich Area / Flexible"
        clean_text = ""

        # Special handler for Apple careers
        if "jobs.apple.com" in url:
            prefix = 'window.__staticRouterHydrationData = JSON.parse('
            start = resp.text.find(prefix)
            if start != -1:
                end_script = resp.text.find('</script>', start)
                line = resp.text[start+len(prefix):end_script].strip()
                if line.endswith(';'): line = line[:-1]
                if line.endswith(')'): line = line[:-1]
                try:
                    obj = json.loads(json.loads(line))
                    jd = obj.get('loaderData', {}).get('jobDetails', {}).get('jobsData', {})
                    title = jd.get('postingTitle') or jd.get('title') or title
                    loc_names = [l.get('city') for l in jd.get('locations', []) if l.get('city')]
                    location = (", ".join(loc_names) + ", Germany") if loc_names else "Munich, Germany"
                    summary = jd.get('jobSummary', '')
                    desc = jd.get('jobDescription', '') or ''
                    quals = '\n'.join(jd.get('keyQualifications', [])) if isinstance(jd.get('keyQualifications'), list) else (jd.get('keyQualifications') or '')
                    clean_text = f"{summary}\n\nKey Qualifications:\n{quals}\n\nDescription:\n{desc}".strip()
                    comp = "Apple"
                    date_posted = jd.get('postingDate') or jd.get('postDateInGMT')
                except Exception as e:
                    print(f"Apple parse error: {e}")

        soup = BeautifulSoup(resp.content, "html.parser")

        # Check for Schema.org JobPosting JSON-LD (used by Infineon, Siemens, Workday, etc.)
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string)
                if isinstance(data, list):
                    data = next((item for item in data if item.get("@type") == "JobPosting"), {})
                if data.get("@type") == "JobPosting":
                    title = data.get("title") or title
                    if (not company or company == "Target Company") and data.get("hiringOrganization", {}).get("name"):
                        comp = data["hiringOrganization"]["name"]
                    job_loc = data.get("jobLocation", {})
                    if isinstance(job_loc, dict):
                        addr = job_loc.get("address", {})
                        loc_city = addr.get("addressLocality") or ""
                        if loc_city:
                            location = f"{loc_city}, Germany"
                    desc_html = data.get("description", "")
                    if desc_html and len(desc_html) > 50:
                        clean_text = clean_html_text(desc_html)
                    if data.get("datePosted"):
                        date_posted = data.get("datePosted")
                    break
            except Exception:
                pass

        if not clean_text:
            title_tag = soup.find("h1") or soup.find("title")
            title = title_tag.get_text().strip() if title_tag else title
            
            for s in soup(["script", "style", "nav", "footer", "header"]):
                s.decompose()
            
            body_text = soup.get_text(separator="\n")
            clean_text = re.sub(r"\n\s*\n", "\n\n", body_text).strip()

        now_iso = datetime.utcnow().isoformat() + "Z"

        return {
            "id": compute_job_id(comp, title, url=url),
            "canonical_url": url,
            "company": comp,
            "title": title,
            "location": location,
            "workplace_type": "remote" if "remote" in title.lower() or "remote" in clean_text[:500].lower() else "hybrid",
            "department": "Engineering & Technology",
            "ats_source": "web_import",
            "raw_content": clean_text[:25000],
            "content_hash": compute_content_hash(f"{title} {clean_text[:5000]}"),
            "discovered_at": now_iso,
            "posted_at": date_posted or now_iso,
            "status": "new"
        }
    except Exception as e:
        print(f"Error fetching arbitrary URL {url}: {e}")
        return None


class SerpApiClient:
    """
    Fetches job listings from Google Jobs via SerpAPI.
    Requires SERPAPI_API_KEY environment variable or Career/.env file.
    """
    BASE_URL = "https://serpapi.com/search.json"

    @classmethod
    def get_api_key(cls) -> Optional[str]:
        key = os.environ.get("SERPAPI_API_KEY")
        if not key:
            env_file = Path(__file__).resolve().parent.parent / ".env"
            if env_file.exists():
                try:
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line.startswith("SERPAPI_API_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if key:
                                break
                except Exception:
                    pass
        return key

    @classmethod
    def search_jobs(cls, query: str, location: str = "Munich, Germany", max_results: int = 15) -> List[Dict[str, Any]]:
        api_key = cls.get_api_key()
        if not api_key:
            return []

        results = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        # 1. Try google_jobs engine first (fast timeout)
        params_jobs = {
            "engine": "google_jobs",
            "q": f"{query} {location}".strip(),
            "hl": "de",
            "gl": "de",
            "api_key": api_key
        }

        try:
            resp = requests.get(cls.BASE_URL, params=params_jobs, headers=HEADERS, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                jobs = data.get("jobs_results", [])
                for j in jobs[:max_results]:
                    title = (j.get("title") or "").strip()
                    company = (j.get("company_name") or "Tech Employer").strip()
                    loc = (j.get("location") or location).strip()
                    desc = (j.get("description") or "").strip()

                    apply_options = j.get("apply_options", [])
                    canonical_url = apply_options[0].get("link", "") if apply_options else ""
                    if not canonical_url:
                        related = j.get("related_links", [])
                        if related:
                            canonical_url = related[0].get("link", "")
                    if not canonical_url:
                        canonical_url = j.get("share_link", "")

                    extensions = j.get("detected_extensions", {})
                    is_wfh = bool(extensions.get("work_from_home", False))
                    workplace_type = "remote" if is_wfh or "remote" in loc.lower() or "remote" in title.lower() else "hybrid"

                    job_id = compute_job_id(company, title, url=canonical_url)
                    chash = compute_content_hash(f"{title} {company} {desc[:2000]}")

                    results.append({
                        "id": job_id,
                        "canonical_url": canonical_url,
                        "company": company,
                        "title": title,
                        "location": loc,
                        "workplace_type": workplace_type,
                        "department": "Engineering & Technology",
                        "ats_source": "serpapi_google_jobs",
                        "raw_content": desc,
                        "content_hash": chash,
                        "discovered_at": now_iso,
                        "posted_at": now_iso,
                        "status": "new"
                    })
        except Exception:
            pass

        if results:
            return results

        # Direct high-coverage Google Search engine targeting verified job boards
        search_q = f'(site:linkedin.com/jobs/view OR site:stepstone.de/stellenangebote OR site:de.indeed.com/viewjob OR "jobs") {query} {location}'.strip()
        params_search = {
            "engine": "google",
            "q": search_q,
            "hl": "de",
            "gl": "de",
            "api_key": api_key
        }

        try:
            resp = requests.get(cls.BASE_URL, params=params_search, headers=HEADERS, timeout=75)
            if resp.status_code == 200:
                data = resp.json()
                
                # Check if organic results contain job postings
                organics = data.get("organic_results", [])
                for o in organics[:max_results]:
                    raw_title = o.get("title", "")
                    link = o.get("link", "")
                    snippet = o.get("snippet", "")

                    # Extract company and role from typical listing formats:
                    # e.g. "Quantum Engineer - QMunicate", "Company sucht Role in Location"
                    company = "Tech Employer"
                    title = raw_title
                    if " - " in raw_title:
                        parts = raw_title.split(" - ")
                        title = parts[0].strip()
                        company = parts[1].split("|")[0].split("·")[0].strip()
                    elif " sucht " in raw_title:
                        parts = raw_title.split(" sucht ", 1)
                        company = parts[0].strip()
                        title = parts[1].split(" in ")[0].strip()
                    elif " at " in raw_title:
                        parts = raw_title.split(" at ", 1)
                        title = parts[0].strip()
                        company = parts[1].split("|")[0].split("·")[0].strip()

                    job_id = compute_job_id(company, title, url=link)
                    chash = compute_content_hash(f"{title} {company} {snippet}")

                    results.append({
                        "id": job_id,
                        "canonical_url": link,
                        "company": company,
                        "title": title,
                        "location": location,
                        "workplace_type": "hybrid",
                        "department": "Engineering & Technology",
                        "ats_source": "serpapi_google_search",
                        "raw_content": f"{raw_title}\n\n{snippet}",
                        "content_hash": chash,
                        "discovered_at": now_iso,
                        "posted_at": now_iso,
                        "status": "new"
                    })
        except Exception as e:
            print(f"SerpAPI search fallback error: {e}")

        return results

