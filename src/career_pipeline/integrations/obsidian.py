"""
career_pipeline.integrations.obsidian - Google OKF v0.2 Vault Adapter
Reads candidate Profile.md/Preferences.md from a private Obsidian vault with multi-region support.
Writes OKF notes to Career/Opportunities/Roles/ and updates Opportunities/index.md and regional indices.
Preserves user application status, original discovered_at dates, and custom notes.
Partitions opportunities into Executive & Leadership vs. Engineering & Technical tracks.
"""
import re
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from ..models import CandidatePersona
from ..generator.typography import slugify
from ..evaluator.matcher import classify_track

def load_vault_persona(vault_career_dir: Path) -> Optional[CandidatePersona]:
    """
    Attempts to read private Profile.md and Preferences.md from Obsidian vault.
    Returns CandidatePersona populated with vault data and regional definitions.
    """
    profile_path = vault_career_dir / "Profile.md"
    if not profile_path.exists():
        return None

    txt = profile_path.read_text(encoding="utf-8")
    name_m = re.search(r"\*\*Name:\*\*\s*([^\r\n]+)", txt)
    title_m = re.search(r"\*\*Title:\*\*\s*([^\r\n]+)", txt)
    loc_m = re.search(r"\*\*Location:\*\*\s*([^\r\n]+)", txt)
    phone_m = re.search(r"\*\*Phone:\*\*\s*([^\r\n]+)", txt)
    email_m = re.search(r"\*\*Email:\*\*\s*([^\r\n\s]+)", txt)
    linkedin_m = re.search(r"\*\*LinkedIn:\*\*\s*\[[^\]]+\]\(([^\)]+)\)", txt)
    github_m = re.search(r"\*\*GitHub:\*\*\s*\[[^\]]+\]\(([^\)]+)\)", txt)

    name = name_m.group(1).strip() if name_m else "Candidate"
    first_name = name.split()[0]
    last_name = " ".join(name.split()[1:]) if " " in name else ""

    addr1 = ""
    addr2 = ""
    if loc_m:
        loc_parts = [p.strip() for p in loc_m.group(1).split(",")]
        addr1 = loc_parts[0] if loc_parts else ""
        addr2 = ", ".join(loc_parts[1:]) if len(loc_parts) > 1 else ""

    # Standardized Multi-Region Configuration (Munich & Berlin)
    regions = {
        "munich": {
            "name": "Munich Metropolitan Area",
            "target_locations": ["munich", "münchen", "garching", "gilching", "martinsried", "taufkirchen", "ottobrunn", "planegg", "karlsfeld", "remote", "germany"],
            "excluded_locations": ["berlin", "london", "paris", "singapore", "tokyo", "lisbon", "warsaw", "usa", "us"]
        },
        "berlin": {
            "name": "Berlin-Brandenburg Area",
            "target_locations": ["berlin", "potsdam", "brandenburg", "wildau", "adlershof", "remote", "germany"],
            "excluded_locations": ["munich", "münchen", "garching", "gilching", "london", "paris", "singapore", "tokyo", "usa", "us"]
        }
    }

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
        target_locations=regions["munich"]["target_locations"],
        excluded_locations=regions["munich"]["excluded_locations"],
        pillars=pillars,
        regions=regions,
        interests=["optics and optical design", "complex autonomous systems", "managing versatile teams on technical challenges"]
    )

def generate_vault_opportunity_note(
    vault_career_dir: Path,
    posting: Dict[str, Any],
    evaluation: Dict[str, Any],
    region: str = "munich"
) -> Path:
    """
    Generates an OKF v0.2 markdown note inside Career/Opportunities/Roles/<slug>.md.
    Preserves existing user status, applied checkboxes, and original discovery dates.
    Includes region tag, career track, and predictive compensation bracket.
    """
    roles_dir = vault_career_dir / "Opportunities" / "Roles"
    roles_dir.mkdir(parents=True, exist_ok=True)

    company = posting.get("company", "Company")
    title = posting.get("title", "Role")
    comp_slug = slugify(company)
    title_slug = slugify(title)[:40]
    filename = f"{comp_slug}-{title_slug}.md"
    file_path = roles_dir / filename

    existing_status = "active"
    existing_tracker = ""
    original_discovered_at = posting.get("discovered_at")
    existing_regions = set()

    if file_path.exists():
        try:
            ex_txt = file_path.read_text(encoding="utf-8")
            status_m = re.search(r'^(?:application_status|status):\s*["\']?(\w+)["\']?', ex_txt, re.MULTILINE)
            if status_m:
                existing_status = status_m.group(1)

            orig_date_m = re.search(r'^(?:discovered_at|at):\s*["\']?([0-9T:.Z+-]+)', ex_txt, re.MULTILINE)
            if orig_date_m and not original_discovered_at:
                original_discovered_at = orig_date_m.group(1)

            reg_m = re.search(r'^regions?:\s*\[?([^\]\r\n]+)\]?', ex_txt, re.MULTILINE)
            if reg_m:
                for r_item in reg_m.group(1).split(","):
                    r_clean = r_item.strip(" \"\'")
                    if r_clean:
                        existing_regions.add(r_clean.lower())

            tracker_m = re.search(r'(## Application & Milestone Tracker.*?)(?:\n---|\Z)', ex_txt, re.DOTALL)
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
    role_track = evaluation.get("role_track") or classify_track(title, archetype)
    location = posting.get("location", "Munich, Germany")
    canonical_url = posting.get("canonical_url", "")
    key_strengths = evaluation.get("key_strengths", [])
    gaps_risks = evaluation.get("gaps_risks", [])

    eval_region = (evaluation.get("region") or region).lower()
    existing_regions.add(eval_region)
    regions_list = sorted(list(existing_regions))
    regions_str = ", ".join(regions_list)

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

    comp = evaluation.get("compensation_estimate") or evaluation.get("compensation") or {}
    if comp:
        b_min = comp.get("base_salary_min", 130000) // 1000
        b_max = comp.get("base_salary_max", 155000) // 1000
        tot_min = comp.get("total_comp_min", 160000) // 1000
        tot_max = comp.get("total_comp_max", 195000) // 1000
        b_pct = int(comp.get("bonus_pct", 0.18) * 100)
        eq = comp.get("equity_type", "None")
        strat = comp.get("negotiation_strategy", "")
        comp_section = f"""## 3. Compensation & Market Valuation
| Component | Estimated Bracket | Target Reference |
| :--- | :--- | :--- |
| **Base Salary** | €{b_min}k – €{b_max}k EUR | Target benchmark base |
| **Variable Bonus** | ~{b_pct}% Target | Corporate / Performance metric |
| **Equity / LTI** | {eq} | Long-term incentive |
| **Total Target Comp** | **€{tot_min}k – €{tot_max}k+ EUR** | €160k – €190k+ target bracket |

> [!TIP]
> **Negotiation Strategy:** {strat}
"""
    else:
        comp_section = """## 3. Compensation & Market Valuation
* Target compensation bracket: €160,000 – €190,000+ EUR total target package."""

    track_badge = "👑 Executive & Leadership" if role_track == "Executive & Leadership" else "🔬 Engineering & Technical"

    pillars_md = "\n".join([f"* **{p}**" for p in evaluation.get("matching_pillars", [])])
    note_content = f"""---
type: Opportunity
title: "{company} — {title}"
description: "Match Score {score}% ({archetype}) in {location}"
resource: "{canonical_url}"
status: {existing_status}
match_score: {score}
role_track: "{role_track}"
role_archetype: "{archetype}"
region: [{regions_str}]
tags: [career, opportunity, {comp_slug}, {eval_region}]
stale_after: {stale_iso}
discovered_at: {disc_iso}
generated:
  by: career-pipeline/v0.3-multiregion
  at: {now_iso}
verified:
  - by: process:career-pipeline
    at: {now_iso}
---

# {company} — {title}

| Attribute | Detail |
| :--- | :--- |
| **Match Score** | **{score} / 100 (Strong Match)** |
| **Career Track** | {track_badge} |
| **Role Archetype** | {archetype} |
| **Target Region** | {eval_region.title()} (Active: {regions_str}) |
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
{pillars_md}

---

## 2. Key Strengths to Pitch
{strengths_md}

---

{comp_section}

---

## 4. Potential Gaps, Risks & Mitigation
{gaps_md}

---

## 5. Application Context
* Generated by `career-pipeline` under Google OKF v0.2 with multi-region and dual-track support.
"""
    file_path.write_text(note_content, encoding="utf-8")
    return file_path

def update_vault_opportunities_index(vault_career_dir: Path):
    """
    Rebuilds Career/Opportunities/index.md and dedicated regional indices (Munich.md, Berlin.md)
    by scanning Career/Opportunities/Roles/*.md.
    Separates Executive & Leadership roles from Engineering & Technical roles with independent rankings.
    Accurately preserves original discovery dates and application tracking checkboxes.
    """
    opp_dir = vault_career_dir / "Opportunities"
    roles_dir = opp_dir / "Roles"
    index_file = opp_dir / "index.md"
    munich_file = opp_dir / "Munich.md"
    berlin_file = opp_dir / "Berlin.md"
    db_path = vault_career_dir / "Data" / "jobs.db"
    roles_dir.mkdir(parents=True, exist_ok=True)

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
        title_m = re.search(r"^title:\s*[\"\']?([^\"\'\r\n]+)", txt, re.MULTILINE)
        score_m = re.search(r'^match_score:\s*([0-9]+)', txt, re.MULTILINE)
        track_m = re.search(r"^role_track:\s*[\"\']?([^\"\'\r\n]+)", txt, re.MULTILINE)
        arch_m = re.search(r"^role_archetype:\s*[\"\']?([^\"\'\r\n]+)", txt, re.MULTILINE)
        res_m = re.search(r"^resource:\s*[\"\']?([^\"\'\r\n]+)", txt, re.MULTILINE)
        disc_m = re.search(r'^(?:discovered_at|at):\s*["\']?([0-9]{4}-[0-9]{2}-[0-9]{2})', txt, re.MULTILINE)
        fm_status_m = re.search(r'^(?:application_status|status):\s*["\']?(\w+)["\']?', txt, re.MULTILINE)
        reg_m = re.search(r'^regions?:\s*\[?([^\]\r\n]+)\]?', txt, re.MULTILINE)

        # Checkbox checks
        applied_box = re.search(r'^\s*-\s*\[[xX]\]\s*(?:\*\*)?Applied', txt, re.MULTILINE)
        applied_at_m = re.search(r'Date:?\s*[`"]?([0-9]{4}-[0-9]{2}-[0-9]{2})[`"]?', txt)
        screening_box = re.search(r'^\s*-\s*\[[xX]\]\s*(?:\*\*)?First Screening', txt, re.MULTILINE)
        interview_box = re.search(r'^\s*-\s*\[[xX]\]\s*(?:\*\*)?(?:Technical Deep Dive|Onsite|Interview)', txt, re.MULTILINE)
        offer_box = re.search(r'^\s*-\s*\[[xX]\]\s*(?:\*\*)?Offer', txt, re.MULTILINE)

        score = int(score_m.group(1)) if score_m else 85
        title = title_m.group(1) if title_m else f.stem
        arch = arch_m.group(1) if arch_m else "Hardware & Systems Leadership"
        track = track_m.group(1).strip() if track_m else classify_track(title, arch)
        res_url = res_m.group(1).strip() if res_m else ""

        # Region detection
        regions_set = {"munich"}
        if reg_m:
            parsed_regs = [r.strip(" \"\'").lower() for r in reg_m.group(1).split(",") if r.strip()]
            if parsed_regs:
                regions_set = set(parsed_regs)
        if "berlin" in f.name.lower() or "berlin" in title.lower():
            regions_set.add("berlin")

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

        entries.append({
            "file": f.name,
            "title": title,
            "score": score,
            "track": track,
            "archetype": arch,
            "date": disc_date,
            "status": status,
            "badge": badge,
            "applied_date": applied_date,
            "regions": regions_set
        })

    applied_entries = [e for e in entries if e["status"] in ["applied", "interviewing", "offer"]]
    applied_entries.sort(key=lambda x: (x.get("applied_date", "") or x.get("date", "")), reverse=True)

    applied_rows = []
    for e in applied_entries:
        reg_badge = ", ".join(sorted(list(e["regions"])))
        track_emoji = "👑" if e["track"] == "Executive & Leadership" else "🔬"
        applied_rows.append(
            f"| {e['badge']} | **{e['score']}%** | [{e['title']}]({e['file']}) | {track_emoji} {e['track']} | {e['applied_date']} | {reg_badge.title()} | {e['archetype']} | [LaTeX Letter](../Tailored_Letters/{e['file'].replace('.md', '.tex')}) |"
        )
    applied_body = "\n".join(applied_rows)
    applied_section = f"""## 📬 Submitted Applications & Pipeline ({len(applied_entries)})

| Status | Match | Opportunity & Company | Track | Applied Date | Region | Role Archetype | Cover Letter |
| :---: | :---: | :--- | :---: | :---: | :---: | :--- | :---: |
{applied_body}

---
""" if applied_entries else ""

    def format_table(items, rel_prefix="Roles/"):
        if not items:
            return "| — | *No active opportunities in this category.* | — | — | — |"
        rows = []
        for e in items:
            rows.append(
                f"| **{e['score']}%** | [{e['title']}]({rel_prefix}{e['file']}) | {e['archetype']} | {e['date']} | {e['badge']} |"
            )
        return "\n".join(rows)

    # Filter by region and career track
    open_entries = [e for e in entries if e["status"] == "open"]
    munich_open = [e for e in open_entries if "munich" in e["regions"]]
    berlin_open = [e for e in open_entries if "berlin" in e["regions"]]

    munich_exec = [e for e in munich_open if e["track"] == "Executive & Leadership"]
    munich_eng = [e for e in munich_open if e["track"] == "Engineering & Technical"]
    munich_exec.sort(key=lambda x: (x["score"], x.get("date", "")), reverse=True)
    munich_eng.sort(key=lambda x: (x["score"], x.get("date", "")), reverse=True)

    berlin_exec = [e for e in berlin_open if e["track"] == "Executive & Leadership"]
    berlin_eng = [e for e in berlin_open if e["track"] == "Engineering & Technical"]
    berlin_exec.sort(key=lambda x: (x["score"], x.get("date", "")), reverse=True)
    berlin_eng.sort(key=lambda x: (x["score"], x.get("date", "")), reverse=True)

    # 1. Master Consolidated Index (index.md)
    master_content = rf"""# Active Career Opportunities & Regional Application Pipeline

Curated, high-fit job opportunities segmented by active job hunting regions and career tracks.
Mark applications directly in each note via checkbox (`- [x] Applied`).

**Regional Quick Links:**
- 🥨 **Munich Pipeline ({len(munich_open)} Total)**: [[Munich|Overview]] • **{len(munich_exec)}** 👑 Executive & Lead • **{len(munich_eng)}** 🔬 Engineering & Technical
- 🐻 **Berlin Pipeline ({len(berlin_open)} Total)**: [[Berlin|Overview]] • **{len(berlin_exec)}** 👑 Executive & Lead • **{len(berlin_eng)}** 🔬 Engineering & Technical

{applied_section}## 🥨 Munich Metropolitan Area (>= 85%) ({len(munich_open)} Total)

### 👑 Executive & Leadership Track ({len(munich_exec)})
*High-responsibility roles: Director, VP, Head of, Chief Engineer, Engineering Manager, Group & Team Lead, Practice Lead.*

| Match | Opportunity & Company | Role Archetype | Discovered | Status |
| :---: | :--- | :--- | :---: | :--- | :---: |
{format_table(munich_exec)}

---

### 🔬 Engineering & Technical Specialist Track ({len(munich_eng)})
*Deep-tech individual contributor and subject-matter specialist roles: Senior Engineer, Optical Physicist, Systems Architect, R&D.*

| Match | Opportunity & Company | Role Archetype | Discovered | Status |
| :---: | :--- | :--- | :---: | :--- | :---: |
{format_table(munich_eng)}

---

## 🐻 Berlin-Brandenburg Area (>= 85%) ({len(berlin_open)} Total)

### 👑 Executive & Leadership Track ({len(berlin_exec)})
*High-responsibility roles: Director, VP, Head of, Chief Engineer, Engineering Manager, Group & Team Lead, Practice Lead.*

| Match | Opportunity & Company | Role Archetype | Discovered | Status |
| :---: | :--- | :--- | :---: | :--- | :---: |
{format_table(berlin_exec)}

---

### 🔬 Engineering & Technical Specialist Track ({len(berlin_eng)})
*Deep-tech individual contributor and subject-matter specialist roles: Senior Engineer, Optical Physicist, Systems Architect, R&D.*

| Match | Opportunity & Company | Role Archetype | Discovered | Status |
| :---: | :--- | :--- | :---: | :--- | :---: |
{format_table(berlin_eng)}

---
*Generated by `career-pipeline` under Google OKF v0.2 with Multi-Region Parallel Ranking & Track Separation.*
"""
    index_file.write_text(master_content, encoding="utf-8")

    # 2. Dedicated Regional Index: Munich.md
    munich_content = rf"""---
type: Directory
title: "Munich Career Opportunities Pipeline"
description: "Curated high-affinity job opportunities in the Munich Metropolitan Area (>= 85%)"
tags: [career, pipeline, munich]
---

# 🥨 Munich Career Opportunities Pipeline

Curated opportunities within a 60-minute commute within the Munich Metropolitan Area or remote Germany.
See also [[index|Master Index]] and [[Berlin|Berlin Pipeline]].

> [!NOTE]
> **Pipeline Breakdown:** **{len(munich_open)} Total Open Positions** across Oberbayern/Remote.
> 👑 **{len(munich_exec)} Executive & Leadership Positions** | 🔬 **{len(munich_eng)} Engineering & Technical Positions**

## 👑 Executive & Leadership Track ({len(munich_exec)})
*High-responsibility roles: Director, VP, Head of, Chief Engineer, Engineering Manager, Group & Team Lead, Practice Lead.*

| Match | Opportunity & Company | Role Archetype | Discovered | Status |
| :---: | :--- | :--- | :---: | :--- | :---: |
{format_table(munich_exec)}

---

## 🔬 Engineering & Technical Specialist Track ({len(munich_eng)})
*Deep-tech individual contributor and subject-matter specialist roles: Senior Engineer, Optical Physicist, Systems Architect, R&D.*

| Match | Opportunity & Company | Role Archetype | Discovered | Status |
| :---: | :--- | :--- | :---: | :--- | :---: |
{format_table(munich_eng)}

---
*Generated by `career-pipeline` under Google OKF v0.2.*
"""
    munich_file.write_text(munich_content, encoding="utf-8")

    # 3. Dedicated Regional Index: Berlin.md
    berlin_content = rf"""---
type: Directory
title: "Berlin Career Opportunities Pipeline"
description: "Curated high-affinity job opportunities in the Berlin-Brandenburg Area (>= 85%)"
tags: [career, pipeline, berlin]
---

# 🐻 Berlin Career Opportunities Pipeline

Curated opportunities within Berlin, Potsdam, or remote Germany.
See also [[index|Master Index]] and [[Munich|Munich Pipeline]].

> [!NOTE]
> **Pipeline Breakdown:** **{len(berlin_open)} Total Open Positions** across Berlin/Brandenburg/Remote.
> 👑 **{len(berlin_exec)} Executive & Leadership Positions** | 🔬 **{len(berlin_eng)} Engineering & Technical Positions**

## 👑 Executive & Leadership Track ({len(berlin_exec)})
*High-responsibility roles: Director, VP, Head of, Chief Engineer, Engineering Manager, Group & Team Lead, Practice Lead.*

| Match | Opportunity & Company | Role Archetype | Discovered | Status |
| :---: | :--- | :--- | :---: | :--- | :---: |
{format_table(berlin_exec)}

---

## 🔬 Engineering & Technical Specialist Track ({len(berlin_eng)})
*Deep-tech individual contributor and subject-matter specialist roles: Senior Engineer, Optical Physicist, Systems Architect, R&D.*

| Match | Opportunity & Company | Role Archetype | Discovered | Status |
| :---: | :--- | :--- | :---: | :--- | :---: |
{format_table(berlin_eng)}

---
*Generated by `career-pipeline` under Google OKF v0.2.*
"""
    berlin_file.write_text(berlin_content, encoding="utf-8")

def generate_vault_digest(vault_career_dir: Path):
    """
    Generates Career/Data/digest.md partitioned by region (Munich & Berlin)
    and by career track (Executive & Leadership vs. Engineering & Technical) for scores 70-84%.
    """
    db_path = vault_career_dir / "Data" / "jobs.db"
    digest_path = vault_career_dir / "Data" / "digest.md"
    if not db_path.exists():
        return

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT p.id, p.company, p.title, p.location, p.canonical_url,
                   e.region, e.fit_score, e.role_archetype, e.role_track
            FROM postings p
            JOIN evaluations e ON p.id = e.posting_id
            WHERE e.fit_score >= 70 AND e.fit_score < 85
            ORDER BY e.fit_score DESC, p.discovered_at DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]

    munich_exec = []
    munich_eng = []
    berlin_exec = []
    berlin_eng = []

    for r in rows:
        reg = (r.get("region") or "munich").lower()
        track = r.get("role_track") or classify_track(r.get("title", ""), r.get("role_archetype", ""))
        r["track"] = track
        if reg == "berlin":
            if track == "Executive & Leadership":
                berlin_exec.append(r)
            else:
                berlin_eng.append(r)
        else:
            if track == "Executive & Leadership":
                munich_exec.append(r)
            else:
                munich_eng.append(r)

    def format_digest_table(items):
        if not items:
            return "| — | *No potential fit opportunities in this category.* | — | — | — |"
        out = []
        for it in items:
            title_link = f"[{it['title']}]({it['canonical_url']})" if it.get("canonical_url") else it["title"]
            out.append(f"| **{it['fit_score']}%** | **{it['company']}** | {title_link} | {it['location']} | {it['role_archetype']} |")
        return "\n".join(out)

    digest_content = f"""# Potential Fit Digest (Score 70% – 84%)

Secondary digest of relevant deep-tech and engineering roles partitioned by region and career track.
Roles in this digest exhibit relevant domain alignment, useful for proactive networking or secondary consideration.

---

## 🥨 Munich Metropolitan Area (70% – 84%) ({len(munich_exec) + len(munich_eng)} Total)

### 👑 Executive & Leadership Track ({len(munich_exec)})
*Lead, Director, Engineering Manager, Head of, and Practice Lead opportunities.*

| Score | Company | Title & Link | Location | Archetype |
| :---: | :--- | :--- | :--- | :--- |
{format_digest_table(munich_exec)}

---

### 🔬 Engineering & Technical Specialist Track ({len(munich_eng)})
*Senior specialist, systems engineering, optical physics, and perception roles.*

| Score | Company | Title & Link | Location | Archetype |
| :---: | :--- | :--- | :--- | :--- |
{format_digest_table(munich_eng)}

---

## 🐻 Berlin-Brandenburg Area (70% – 84%) ({len(berlin_exec) + len(berlin_eng)} Total)

### 👑 Executive & Leadership Track ({len(berlin_exec)})
*Lead, Director, Engineering Manager, Head of, and Practice Lead opportunities.*

| Score | Company | Title & Link | Location | Archetype |
| :---: | :--- | :--- | :--- | :--- |
{format_digest_table(berlin_exec)}

---

### 🔬 Engineering & Technical Specialist Track ({len(berlin_eng)})
*Senior specialist, systems engineering, optical physics, and perception roles.*

| Score | Company | Title & Link | Location | Archetype |
| :---: | :--- | :--- | :--- | :--- |
{format_digest_table(berlin_eng)}

---
*Generated by `career-pipeline` under Google OKF v0.2 with Multi-Region Parallel Ranking & Track Separation.*
"""
    digest_path.write_text(digest_content, encoding="utf-8")
