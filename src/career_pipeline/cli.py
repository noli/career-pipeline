import os
"""
career_pipeline.cli - Unified Command Line Interface
Cross-platform entrypoint supporting both standalone operation and Obsidian vault linking.
"""
import sys
import json
import argparse
from pathlib import Path
from typing import Optional

from .config import load_yaml, load_persona, DEFAULT_CONFIG
from .models import CandidatePersona
from .storage.db import init_db, is_seen, upsert_posting, save_evaluation, get_unscored_postings, get_stats, get_db_connection
from .evaluator.matcher import evaluate_job
from .generator.letter_engine import generate_cover_letter
from .generator.tectonic import is_tectonic_installed
from .integrations.obsidian import load_vault_persona, generate_vault_opportunity_note, update_vault_opportunities_index
from .integrations.apple_mail import export_apple_mail_alerts
from .integrations.email_inbox import process_inbox_directory
from .scrapers.ats_clients import (
    GreenhouseClient, LeverClient, PersonioClient, TeamtailorClient,
    MQVClient, RecruiteeClient, AshbyClient, TopticaClient, SmartRecruitersClient,
    WorkdayClient, SuccessFactorsClient, AvatureClient, MTUClient,
    SerpApiClient, fetch_arbitrary_url
)

def scan_ats(db_path: Path, companies_path: Path, verbose: bool = True) -> int:
    if not companies_path.exists():
        print(f"Target companies registry not found at {companies_path}")
        return 0

    with open(companies_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    companies = registry.get("companies", [])
    new_jobs = 0

    for comp in companies:
        if not comp.get("enabled", True):
            continue
        ats_type = comp.get("ats_type", "").lower()
        name = comp["name"]
        ats_id = comp.get("ats_id", "")
        ats_config = comp.get("ats_config", {})
        loc_filter = comp.get("location_filter")

        try:
            postings = []
            if ats_type == "greenhouse":
                postings = GreenhouseClient.fetch_jobs(ats_id, name, loc_filter)
            elif ats_type == "lever":
                postings = LeverClient.fetch_jobs(ats_id, name, loc_filter)
            elif ats_type == "personio":
                postings = PersonioClient.fetch_jobs(ats_id, name, loc_filter)
            elif ats_type == "teamtailor":
                postings = TeamtailorClient.fetch_jobs(ats_id, name, loc_filter)
            elif ats_type == "recruitee":
                postings = RecruiteeClient.fetch_jobs(ats_id, name, loc_filter)
            elif ats_type == "ashby":
                postings = AshbyClient.fetch_jobs(ats_id, name, loc_filter)
            elif ats_type == "smartrecruiters":
                postings = SmartRecruitersClient.fetch_jobs(ats_id, name, loc_filter)
            elif ats_type == "workday":
                postings = WorkdayClient.fetch_jobs(ats_config, name, loc_filter)
            elif ats_type == "successfactors":
                postings = SuccessFactorsClient.fetch_jobs(ats_config, name, loc_filter)
            elif ats_type == "avature":
                postings = AvatureClient.fetch_jobs(ats_config, name, loc_filter)
            elif ats_type == "mqv":
                postings = MQVClient.fetch_jobs()
            elif ats_type == "toptica":
                postings = TopticaClient.fetch_jobs(loc_filter)
            elif ats_type == "mtu":
                postings = MTUClient.fetch_jobs(loc_filter, name)

            for p in postings:
                if not is_seen(db_path, p["canonical_url"]):
                    upsert_posting(db_path, p)
                    new_jobs += 1
                    if verbose:
                        print(f"  [+] Discovered: {p['company']} - {p['title']}")
        except Exception as e:
            if verbose:
                print(f"  [!] Error scraping {comp['name']}: {e}")

    return new_jobs

def run_evaluation(db_path: Path, persona: CandidatePersona, verbose: bool = True) -> int:
    unscored = get_unscored_postings(db_path)
    if verbose:
        print(f"Evaluating {len(unscored)} postings against persona...")

    scored_count = 0
    for p in unscored:
        eval_res = evaluate_job(p, persona)
        save_evaluation(db_path, eval_res)
        scored_count += 1
        if verbose and eval_res["fit_score"] >= 85:
            print(f"  [Match {eval_res['fit_score']}%] {p['company']} - {p['title']} ({eval_res['role_archetype']})")

    return scored_count

def main():
    parser = argparse.ArgumentParser(description="Autonomous Cross-Platform Career Job Pipeline")
    parser.add_argument("--all", action="store_true", help="Run full discovery, evaluation, and generation")
    parser.add_argument("--scan-ats", action="store_true", help="Query registered company ATS boards")
    parser.add_argument("--url", type=str, help="Ad-hoc ingestion of a single job posting URL")
    parser.add_argument("--company", type=str, default="", help="Company name for ad-hoc URL")
    parser.add_argument("--evaluate", action="store_true", help="Score all unscored postings in the database")
    parser.add_argument("--generate", action="store_true", help="Generate opportunity notes and letters for high matches")
    parser.add_argument("--stats", action="store_true", help="Print pipeline database metrics")
    parser.add_argument("--inbox", action="store_true", help="Parse .eml/.msg files from inbox directory")
    parser.add_argument("--sync-mail", action="store_true", help="Sync alert emails from Apple Mail (macOS only)")
    parser.add_argument("--vault-path", type=str, help="Path to private Obsidian Career vault folder")
    parser.add_argument("--config", type=str, help="Path to custom config.yaml")
    parser.add_argument("--persona", type=str, help="Path to custom persona.yaml")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent
    
    # Auto-load .env from repo root if present
    env_file = repo_root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    # Vault mode vs Standalone mode
    vault_path_val = args.vault_path or os.getenv("CAREER_VAULT_PATH")
    vault_dir = Path(vault_path_val).resolve() if vault_path_val else None
    
    if vault_dir and vault_dir.exists():
        print(f"[Mode] Obsidian Vault Integration: {vault_dir}")
        db_path = vault_dir / "Data" / "jobs.db"
        companies_path = vault_dir / "Data" / "target_companies.json"
        if not companies_path.exists():
            companies_path = repo_root / "configs" / "target_companies.json"
        
        # Load persona from vault Profile.md, fallback to persona.yaml
        persona = load_vault_persona(vault_dir)
        if not persona:
            persona_file = Path(args.persona) if args.persona else (repo_root / "configs" / "persona.example.yaml")
            persona = load_persona(persona_file)
    else:
        print("[Mode] Standalone CLI Mode")
        db_path = repo_root / "data" / "jobs.db"
        companies_path = repo_root / "configs" / "target_companies.json"
        persona_file = Path(args.persona) if args.persona else (repo_root / "configs" / "persona.example.yaml")
        persona = load_persona(persona_file)

    init_db(db_path)

    # If no specific action specified, default to --stats or --all
    if not (args.all or args.scan_ats or args.url or args.evaluate or args.generate or args.stats or args.inbox or args.sync_mail):
        args.stats = True

    if args.stats:
        stats = get_stats(db_path)
        print("\n=== Pipeline Database Metrics ===")
        print(f"Total Postings:          {stats['total_postings']}")
        print(f"High Fit (>= 85%):       {stats['high_fit_85_plus']}")
        print(f"Potential Fit (70-84%):  {stats['potential_fit_70_84']}")
        print(f"Low Fit (< 70%):         {stats['low_fit_below_70']}")
        print(f"Tectonic PDF Compiler:   {'Installed' if is_tectonic_installed() else 'Not found'}")
        print("=================================\n")

    if args.sync_mail:
        inbox_dir = (vault_dir / "Inbox") if vault_dir else (repo_root / "data" / "inbox")
        exported = export_apple_mail_alerts(inbox_dir)
        print(f"Exported {exported} alerts from Apple Mail.")
        args.inbox = True

    if args.inbox:
        inbox_dir = (vault_dir / "Inbox") if vault_dir else (repo_root / "data" / "inbox")
        archive_dir = inbox_dir / "Archive"
        postings = process_inbox_directory(inbox_dir, archive_dir)
        print(f"Extracted {len(postings)} jobs from email inbox.")
        for p in postings:
            if not is_seen(db_path, p["canonical_url"]):
                upsert_posting(db_path, p)

    if args.scan_ats or args.all:
        print("Scanning target ATS boards...")
        new_jobs = scan_ats(db_path, companies_path)
        print(f"Discovered {new_jobs} new job postings.")

    if args.url:
        print(f"Ingesting URL: {args.url}")
        p = fetch_arbitrary_url(args.url, company=args.company)
        if p:
            upsert_posting(db_path, p)
            args.evaluate = True

    if args.evaluate or args.all:
        scored = run_evaluation(db_path, persona)
        print(f"Scored {scored} postings.")

    if args.generate or args.all:
        if vault_dir:
            print("Generating OKF Opportunity Notes and Vault Index...")
            with get_db_connection(db_path) as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT p.*, e.fit_score, e.role_archetype, e.matching_pillars, e.key_strengths, e.gaps_risks, e.pitch_strategy
                    FROM postings p JOIN evaluations e ON p.id = e.posting_id
                    WHERE e.fit_score >= 85
                """)
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    if isinstance(r.get("matching_pillars"), str):
                        r["matching_pillars"] = [x.strip() for x in r["matching_pillars"].split(",") if x.strip()]
                    if isinstance(r.get("key_strengths"), str):
                        r["key_strengths"] = [x.strip() for x in r["key_strengths"].split("|") if x.strip()]
                    if isinstance(r.get("gaps_risks"), str):
                        r["gaps_risks"] = [x.strip() for x in r["gaps_risks"].split("|") if x.strip()]
                    generate_vault_opportunity_note(vault_dir, r, r)
            update_vault_opportunities_index(vault_dir)
            print("Vault opportunities synchronized successfully.")
        else:
            print("Generation complete in standalone mode.")

if __name__ == "__main__":
    main()
