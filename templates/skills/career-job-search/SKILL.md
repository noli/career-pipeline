---
name: career-job-search
description: Automated job discovery, scoring, application preparation, and PDF compilation pipeline. Scans target company ATS boards, evaluates fit against candidate profile, deduplicates in SQLite, drafts tailored LaTeX letters, and compiles production-ready PDFs via Tectonic.
---

# Career Job Search & Application Pipeline Skill

This skill encapsulates the autonomous job hunting, evaluation, and application drafting pipeline powered by the decoupled `career-pipeline` toolsuite.

## Domain Separation & Isolation

To ensure complete modularity and prevent crossover with personal notes:
* **Execution Boundary:** All scraping, scoring, and compilation logic resides in the standalone repository `career-pipeline`.
* **Knowledge Vault Integration:** When linked via `--vault-path <PATH>` (or `CAREER_VAULT_PATH` in `.env`), the tool reads private profiles and writes:
  - `Career/Data/`: Persistent storage (`jobs.db` SQLite database, `target_companies.json`, `digest.md`).
  - `Career/Opportunities/`: Google OKF v0.2 directory containing `index.md` at root, and individual role notes in `Career/Opportunities/Roles/<slug>.md`.
  - `Career/Tailored_Letters/`: Tailored LaTeX cover letters with sanitized typography.
  - `Career/PDFs/`: Production-ready cover letter PDFs compiled headlessly via **Tectonic**.
* **Zero PII Contamination:** The toolsuite repository contains zero personal data, while private candidate notes and database remain safely in the private vault.

---

## Quick Reference CLI Commands

All commands run using `uv` targeting the `career-pipeline` project (or direct global CLI):

### 1. Run Full Discovery & Evaluation (ATS + Web + Scoring + Letters)
```bash
uv run --project /path/to/career-pipeline career-pipeline --all
```

### 2. Ingest and Score an Arbitrary Job URL (e.g. from LinkedIn or Recruiter)
```bash
uv run --project /path/to/career-pipeline career-pipeline --url "https://jobs.example.com/details/..." --company "ExampleTech"
```
*Fetches the job, normalizes it, scores it against candidate profile, saves to `jobs.db`, and if >= 85%, generates both the OKF Opportunity note in `Opportunities/Roles/` and tailored LaTeX letter.*

### 3. Check Pipeline Metrics & Status
```bash
uv run --project /path/to/career-pipeline career-pipeline --stats
```

### 4. Ingest Email Job Alerts from Career/Inbox/
```bash
uv run --project /path/to/career-pipeline career-pipeline --inbox
```
*Parses all pending `.eml` / `.msg` files in `Career/Inbox/`, extracts positions, scores them against profile, updates the database, and moves processed emails to `Career/Inbox/Archive/`.*

### 5. Sync Job Alerts Directly from Apple Mail (macOS)
```bash
uv run --project /path/to/career-pipeline career-pipeline --sync-mail
```
*Queries macOS Apple Mail for matching alerts, exports them to `Career/Inbox/`, and executes the full ingestion pipeline.*

---

## Automated LaTeX & PDF Compilation (Tectonic Engine)

All programmatic PDF compilation is handled locally:
1. **Engine:** `tectonic` (XeTeX-based modern TeX engine with automatic package caching).
2. **Artifact Output:**
   - LaTeX source: `Career/Tailored_Letters/<company>_<title>.tex`
   - Compiled PDF: `Career/PDFs/<company>_<title>.pdf`
   - Referenced simultaneously in `Career/Opportunities/Roles/<company>-<title>.md`

---

## Target Companies & ATS Registry

Monitored companies are configured in `Career/Data/target_companies.json` (or `configs/target_companies.json`).
Supported ATS engines & connectors:
- **Greenhouse:** Direct JSON API (`boards-api.greenhouse.io` / `job-boards.eu.greenhouse.io`)
- **Lever:** Direct JSON API (`api.lever.co`)
- **Personio:** REST JSON & XML feeds (`{id}.jobs.personio.de`)
- **Teamtailor:** Direct JSON feeds (`{id}.teamtailor.com/jobs.json`)
- **Recruitee:** Direct REST API (`career.{domain}.com/api/offers/`)
- **Ashby:** Direct JSON API (`api.ashbyhq.com`)
- **SmartRecruiters:** Direct REST API (`api.smartrecruiters.com`)
- **Workday:** Public REST API (`/wday/cxs/{tenant}/{site}/jobs`)
- **SerpAPI (Google Jobs Engine):** Multi-portal aggregator across LinkedIn, StepStone, Indeed, Xing.
- **Corporate Web Harvester:** Schema.org `JobPosting` and Next/React hydration.
