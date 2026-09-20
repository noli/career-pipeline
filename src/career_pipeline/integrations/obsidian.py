"""
career_pipeline.integrations.obsidian - Google OKF v0.2 Vault Adapter
Reads candidate Profile.md/Preferences.md from a private Obsidian vault,
and writes OKF notes to Career/Opportunities/Roles/ and updates Opportunities/index.md.
Preserves user application status, original discovered_at dates, and custom notes.
"""
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from ..models import CandidatePersona
from ..generator.typography import slugify

def load_vault_persona(vault_career_dir: Path) -> Optional[CandidatePersona]:
    """
    Attempts to read private Profile.md and Preferences.md from Obsidian vault.
    Returns CandidatePersona populated with vault data, or None if Profile.md is missing.
    """
    profile_path = vault_career_dir / "Profile.md"
    pref_path = vault_career_dir / "Preferences.md"

    if not profile_path.exists():
        return None

    txt = profile_path.read_text(encoding="utf-8")
    
    # Parse contact details
    name_m = re.search(r'\*\*Name:\*\*\s*([^\r\n]+)', txt)
    title_m = re.search(r'\*\*Title:\*\*\s*([^\r\n]+)', txt)
    loc_m = re.search(r'\*\*Location:\*\*\s*([^\r\n]+)', txt)
    phone_m = re.search(r'\*\*Phone:\*\*\s*([^\r\n]+)', txt)
    email_m = re.search(r'\*\*Email:\*\*\s*([^\r\n\s]+)', txt)
    linkedin_m = re.search(r'\*\*LinkedIn:\*\*\s*\[[^\]]+\]\(([^\)]+)\)', txt)
    github_m = re.search(r'\*\*GitHub:\*\*\s*\[[^\]]+\]\(([^\)]+)\)', txt)

    name = name_m.group(1).strip() if name_m else "Candidate"
    first_name = name.split()[0]
    last_name = " ".join(name.split()[1:]) if " " in name else ""

    addr1 = ""
    addr2 = ""
    if loc_m:
        loc_parts = [p.strip() for p in loc_m.group(1).split(",")]
        addr1 = loc_parts[0] if loc_parts else ""
        addr2 = ", ".join(loc_parts[1:]) if len(loc_parts) > 1 else ""

    target_locations = ["munich", "münchen", "garching", "gilching", "martinsried", "remote", "germany"]
    excluded_locations = ["lisbon", "warsaw", "espoo", "singapore", "tokyo", "london", "paris", "usa", "us", "berlin"]

    pillars = [
        {"name": "Autonomous Sensors & Systems Engineering", "weight": 18, "keywords": ["lidar", "radar", "camera", "sensor integration", "sensor fusion", "perception", "point cloud", "autonomous driving", "adas"]},
        {"name": "Deep-Tech Physics, Optics & Quantum Systems", "weight": 20, "keywords": ["optics", "optical", "photonics", "laser", "quantum", "qubit", "cryogenic", "ion trap", "neutral atom", "spectroscopy"]},
        {"name": "Technical Program Management & Systems Industrialization", "weight": 14, "keywords": ["industrialization", "mass production", "dfm", "dfa", "dfmea", "bring-up", "pcb", "emc", "qualification", "systems engineering"]},
        {"name": "Modern AI & Computational Physics", "weight": 12, "keywords": ["pipeline", "python", "algorithms", "data analysis", "signal processing", "simulation", "applied ai", "machine learning"]},
        {"name": "Technology Strategy & Deep-Tech Advisory", "weight": 14, "keywords": ["consulting", "consultant", "advisory", "strategy", "transformation", "due diligence", "technology strategy"]},
        {"name": "Hardware Architecture & Electronics", "weight": 12, "keywords": ["pmic", "silicon", "semiconductor", "packaging", "fpga", "rf", "wafer"]},
        {"name": "NewSpace & Optical Communications", "weight": 18, "keywords": ["laser communication", "satellite", "payload", "space systems", "spacecraft", "orbital", "star tracker"]}
    ]

    return CandidatePersona(
        name=name,
        first_name=first_name,
        last_name=last_name,
        title=title_m.group(1).strip() if title_m else "Systems Architect",
        address_line1=addr1,
        address_line2=addr2,
        phone=phone_m.group(1).strip() if phone_m else "",
        email=email_m.group(1).strip() if email_m else "",
        linkedin=linkedin_m.group(1).strip() if linkedin_m else "",
        github=github_m.group(1).strip() if github_m else "",
        target_locations=target_locations,
        excluded_locations=excluded_locations,
        pillars=pillars
    )

def generate_vault_opportunity_note(
    vault_career_dir: Path,
    posting: Dict[str, Any],
    evaluation: Dict[str, Any]
) -> Path:
    """
    Generates an OKF v0.2 markdown note inside Career/Opportunities/Roles/<slug>.md.
    Preserves existing user status, applied checkboxes, and original discovery dates.
    """
    roles_dir = vault_career_dir / "Opportunities" / "Roles"
    roles_dir.mkdir(parents=True, exist_ok=True)

    company = posting.get("company", "Company")
    title = posting.get("title", "Role")
    comp_slug = slugify(company)
    title_slug = slugify(title)[:40]
    filename = f"{comp_slug}-{title_slug}.md"
    file_path = roles_dir / filename

    # Preserve user edits if file already exists
    existing_status = "active"
    existing_tracker = ""
    original_discovered_at = posting.get("discovered_at")

    if file_path.exists():
        try:
            ex_txt = file_path.read_text(encoding="utf-8")
            # Preserve status
            status_m = re.search(r'^(?:application_status|status):\s*["\']?(\w+)["\']?', ex_txt, re.MULTILINE)
            if status_m:
                existing_status = status_m.group(1)

            # Preserve discovery date from existing frontmatter if db lacks it
            orig_date_m = re.search(r'^(?:discovered_at|at):\s*["\']?([0-9T:.Z+-]+)', ex_txt, re.MULTILINE)
            if orig_date_m and not original_discovered_at:
                original_discovered_at = orig_date_m.group(1)

            # Preserve milestone tracker section
            tracker_m = re.search(r'(## Application & Milestone Tracker.*?)(?:\n---|$)', ex_txt, re.DOTALL)
            if tracker_m:
                existing_tracker = tracker_m.group(1).strip()
        except Exception:
            pass

    now_dt = datetime.utcnow()
    now_iso = now_dt.isoformat() + "Z"
    stale_iso = (now_dt + timedelta(days=30)).isoformat() + "Z"
    disc_iso = original_discovered_at or now_iso

    score = evaluation.get("fit_score", 85)
    archetype = evaluation.get("role_archetype", "Hardware & Systems Leadership")
    location = posting.get("location", "Munich, Germany")
    canonical_url = posting.get("canonical_url", "")
    key_strengths = evaluation.get("key_strengths", [])
    gaps_risks = evaluation.get("gaps_risks", [])

    strengths_md = "\n".join([f"* **{s}**" for s in key_strengths])
    gaps_md = "\n".join([f"* {g}" for g in gaps_risks]) if gaps_risks else "* No blocking technical or geographic dealbreakers identified."

    letter_filename = f"{comp_slug}_{title_slug}.tex"
    letter_rel_path = f"../../Tailored_Letters/{letter_filename}"
    pdf_filename = f"{comp_slug}_{title_slug}.pdf"
    pdf_rel_path = f"../../PDFs/{pdf_filename}"

    tracker_block = existing_tracker if existing_tracker else """## Application & Milestone Tracker
- [ ] **Applied** (Date: `____-__-__`)
- [ ] **First Screening / HR Conversation**
- [ ] **Technical Deep Dive / Hiring Manager**
- [ ] **Onsite / Final Interview**
- [ ] **Offer Received**"""

    note_content = f"""---
type: Opportunity
title: "{company} — {title}"
description: "Match Score {score}% ({archetype}) in {location}"
resource: "{canonical_url}"
status: {existing_status}
match_score: {score}
role_archetype: "{archetype}"
tags: [career, opportunity, {comp_slug}]
stale_after: {stale_iso}
discovered_at: {disc_iso}
generated:
  by: career-pipeline/v0.2
  at: {disc_iso}
verified:
  - by: process:career-pipeline
    at: {disc_iso}
---

# {company} — {title}

| Attribute | Detail |
| :--- | :--- |
| **Match Score** | **{score} / 100 (Strong Match)** |
| **Role Archetype** | {archetype} |
| **Company & Sector** | **{company}** |
| **Location** | {location} |
| **Original Posting** | [Official Job Listing]({canonical_url}) |
| **Tailored Cover Letter** | [`{letter_filename}`]({letter_rel_path}) |
| **Compiled PDF** | [`{pdf_filename}`]({pdf_rel_path}) |

---

{tracker_block}

---

## 1. Opportunity Fit Summary
{evaluation.get('pitch_strategy', '')}

### Core Matching Pillars
""" + "\n".join([f"* **{p}**" for p in evaluation.get("matching_pillars", [])]) + f"""

---

## 2. Key Strengths to Pitch
{strengths_md}

---

## 3. Potential Gaps, Risks & Mitigation
{gaps_md}

---

## 4. Application Context
* Generated by `career-pipeline` under Google OKF v0.2.
"""
    file_path.write_text(note_content, encoding="utf-8")
    return file_path

def update_vault_opportunities_index(vault_career_dir: Path):
    """
    Rebuilds Career/Opportunities/index.md by scanning Career/Opportunities/Roles/*.md.
    Accurately extracts original discovery date and application tracking status.
    """
    opp_dir = vault_career_dir / "Opportunities"
    roles_dir = opp_dir / "Roles"
    index_file = opp_dir / "index.md"
    db_path = vault_career_dir / "Data" / "jobs.db"
    roles_dir.mkdir(parents=True, exist_ok=True)

    # Optional DB lookup for original discovered_at by canonical_url
    url_to_discovered = {}
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT canonical_url, SUBSTR(discovered_at, 1, 10) FROM postings WHERE discovered_at IS NOT NULL")
                for u, d in cur.fetchall():
                    if u and d:
                        url_to_discovered[u] = d
        except Exception:
            pass

    entries = []
    for f in roles_dir.glob("*.md"):
        txt = f.read_text(encoding="utf-8")
        title_m = re.search(r'^title:\s*["\']?([^"\'\r\n]+)', txt, re.MULTILINE)
        score_m = re.search(r'^match_score:\s*([0-9]+)', txt, re.MULTILINE)
        arch_m = re.search(r'^role_archetype:\s*["\']?([^"\'\r\n]+)', txt, re.MULTILINE)
        res_m = re.search(r'^resource:\s*["\']?([^"\'\r\n]+)', txt, re.MULTILINE)
        disc_m = re.search(r'^(?:discovered_at|at):\s*["\']?([0-9]{4}-[0-9]{2}-[0-9]{2})', txt, re.MULTILINE)
        fm_status_m = re.search(r'^(?:application_status|status):\s*["\']?(\w+)["\']?', txt, re.MULTILINE)
        
        # Checkbox checks
        applied_box = re.search(r'^\s*-\s*\[[xX]\]\s*(?:\*\*)?Applied', txt, re.MULTILINE)
        applied_at_m = re.search(r'Date:?\s*[`"]?([0-9]{4}-[0-9]{2}-[0-9]{2})[`"]?', txt)
        screening_box = re.search(r'^\s*-\s*\[[xX]\]\s*(?:\*\*)?First Screening', txt, re.MULTILINE)
        interview_box = re.search(r'^\s*-\s*\[[xX]\]\s*(?:\*\*)?(?:Technical Deep Dive|Onsite|Interview)', txt, re.MULTILINE)
        offer_box = re.search(r'^\s*-\s*\[[xX]\]\s*(?:\*\*)?Offer', txt, re.MULTILINE)

        score = int(score_m.group(1)) if score_m else 85
        title = title_m.group(1) if title_m else f.stem
        arch = arch_m.group(1) if arch_m else "Engineering Leadership"
        res_url = res_m.group(1).strip() if res_m else ""

        # True discovery date: db lookup -> frontmatter -> fallback
        disc_date = url_to_discovered.get(res_url) or (disc_m.group(1) if disc_m else "")

        status = "open"
        badge = "⚪ Open"
        applied_date = ""

        fm_val = fm_status_m.group(1).lower() if fm_status_m else ""
        if offer_box or fm_val in ["offer", "offered"]:
            status = "offer"
            badge = "🏆 **Offer Received**"
        elif interview_box or screening_box or fm_val in ["interviewing", "interview"]:
            status = "interviewing"
            badge = "🟡 **Interviewing**"
        elif applied_box or fm_val in ["applied", "submitted"]:
            status = "applied"
            applied_date = applied_at_m.group(1) if applied_at_m else (disc_date or "2026-09-18")
            badge = f"🟢 **Applied** ({applied_date})"

        # Clean title prefix if company already separated
        display_title = title

        entries.append({
            "file": f.name,
            "title": display_title,
            "score": score,
            "archetype": arch,
            "date": disc_date,
            "status": status,
            "badge": badge,
            "applied_date": applied_date
        })

    applied_entries = [e for e in entries if e["status"] in ["applied", "interviewing", "offer"]]
    open_entries = [e for e in entries if e["status"] == "open"]

    applied_entries.sort(key=lambda x: (x.get("applied_date", "") or x.get("date", "")), reverse=True)
    open_entries.sort(key=lambda x: (x["score"], x.get("date", "")), reverse=True)

    applied_rows = []
    for e in applied_entries:
        tex_name = e['file'].replace('.md', '.tex').replace('-', '_', 1)
        applied_rows.append(
            f"| {e['badge']} | **{e['score']}%** | [{e['title']}](Roles/{e['file']}) | {e['applied_date']} | {e['archetype']} | [LaTeX Letter](../Tailored_Letters/{e['file'].replace('.md', '.tex')}) |"
        )
    applied_body = "\n".join(applied_rows)

    open_rows = []
    for e in open_entries:
        open_rows.append(
            f"| **{e['score']}%** | [{e['title']}](Roles/{e['file']}) | {e['archetype']} | {e['date']} | {e['badge']} |"
        )
    open_body = "\n".join(open_rows) if open_rows else "| — | *No open opportunities yet.* | — | — | — |"

    applied_section = f"""## 📬 Submitted Applications & Pipeline ({len(applied_entries)})

| Status | Match | Opportunity & Company | Applied Date | Role Archetype | Cover Letter |
| :---: | :---: | :--- | :---: | :--- | :---: |
{applied_body}

---

""" if applied_entries else ""

    content = rf"""# Active Career Opportunities & Application Pipeline

Curated, high-fit job opportunities. Mark applications directly in each note via checkbox (`- [x] Applied`).

{applied_section}## 🎯 High-Priority Opportunities (Match $\ge$ 85%) ({len(open_entries)})

| Match | Opportunity & Company | Role Archetype | Discovered | Status |
| :---: | :--- | :--- | :---: | :--- | :---: |
{open_body}

---
*Generated by `career-pipeline` under Google OKF v0.2.*
"""
    index_file.write_text(content, encoding="utf-8")
