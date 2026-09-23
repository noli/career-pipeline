"""
career_pipeline.cli - Command Line Interface & Multi-Agent Orchestrator Dispatcher
Cross-platform entrypoint supporting multi-region parallel job evaluation (Munich & Berlin),
predictive compensation modeling, and autonomous subagent execution.
"""
import os
import sys
import argparse
from pathlib import Path

from .models import CandidatePersona
from .storage.db import init_db, get_stats, get_db_connection, compute_job_id, upsert_posting
from .config import load_config, load_persona
from .agents import CareerOrchestrator, JobHarvesterSubagent, FitEvaluatorSubagent, WriterAndCompSubagent
from .integrations.obsidian import load_vault_persona
from .integrations.apple_mail import export_apple_mail_alerts
from .scrapers.ats_clients import fetch_arbitrary_url as fetch_single_job

def main():
    parser = argparse.ArgumentParser(description="Autonomous Cross-Platform Multi-Agent Career Pipeline")
    parser.add_argument("--all", action="store_true", help="Run full multi-agent pipeline: Ingestion, Multi-Region Evaluation, Letters & PDF compilation")
    parser.add_argument("--scan-ats", action="store_true", help="Query registered company ATS boards")
    parser.add_argument("--url", type=str, help="Ad-hoc ingestion of a single job posting URL")
    parser.add_argument("--company", type=str, default="", help="Company name for ad-hoc URL")
    parser.add_argument("--evaluate", action="store_true", help="Score all unscored postings across regions")
    parser.add_argument("--generate", action="store_true", help="Generate opportunity notes, cover letters, and PDFs for high matches")
    parser.add_argument("--no-compile", action="store_true", help="Skip headless Tectonic PDF compilation")
    parser.add_argument("--region", type=str, default="all", choices=["all", "munich", "berlin"], help="Target region for evaluation (default: all)")
    parser.add_argument("--stats", action="store_true", help="Print pipeline database metrics broken down by region")
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

    # Check for Obsidian Vault integration
    vault_path_val = args.vault_path or os.getenv("CAREER_VAULT_PATH")
    vault_dir = Path(vault_path_val).resolve() if vault_path_val else None

    if vault_dir and vault_dir.exists():
        print(f"[Mode] Obsidian Vault Integration: {vault_dir}")
        db_path = vault_dir / "Data" / "jobs.db"
        companies_path = vault_dir / "Data" / "target_companies.json"
        template_path = repo_root / "templates" / "cover_letter.tex.jinja"
        inbox_dir = vault_dir / "Inbox"
        persona = load_vault_persona(vault_dir)
        if not persona:
            print("Warning: Could not parse Profile.md from vault. Falling back to persona.yaml")
            persona = load_persona(args.persona or str(repo_root / "configs" / "persona.example.yaml"))
    else:
        print("[Mode] Standalone Toolsuite")
        db_path = repo_root / "data" / "jobs.db"
        companies_path = repo_root / "configs" / "target_companies.example.json"
        template_path = repo_root / "templates" / "cover_letter.tex.jinja"
        inbox_dir = repo_root / "data" / "inbox"
        persona = load_persona(args.persona or str(repo_root / "configs" / "persona.example.yaml"))

    init_db(db_path)

    # Initialize Career Orchestrator
    orchestrator = CareerOrchestrator(
        db_path=db_path,
        persona=persona,
        vault_dir=vault_dir,
        companies_path=companies_path,
        template_path=template_path,
        inbox_dir=inbox_dir
    )

    target_regions = ["munich", "berlin"] if args.region == "all" else [args.region]

    if args.stats:
        stats = get_stats(db_path)
        print("\n=== Pipeline Multi-Region Metrics ===")
        print(f"Total Postings Tracked: {stats['total_postings']}")
        for reg, r_stat in stats.get("regions", {}).items():
            print(f"  [{reg.upper()} Region] High Fit (>= 85%): {r_stat['high_fit']} | Potential (70-84%): {r_stat['potential_fit']} | Pruned: {r_stat['low_fit']}")
        print("=====================================\n")
        return

    if args.all:
        orchestrator.run_full_pipeline(regions=target_regions, compile_pdf=not args.no_compile)
        return

    if args.sync_mail:
        count = export_apple_mail_alerts(inbox_dir)
        print(f"Exported {count} job alerts from Apple Mail into {inbox_dir}")
        args.inbox = True

    if args.inbox or args.scan_ats:
        res = orchestrator.harvester.crawl_all(companies_path=companies_path, inbox_dir=inbox_dir)
        print(f"Discovered {res['total_new']} new job postings.")

    if args.url:
        job = fetch_single_job(args.url, args.company)
        if job:
            job_id = upsert_posting(db_path, job)
            print(f"Ingested ad-hoc posting: {job['company']} - {job['title']} ({job_id})")
            args.evaluate = True

    if args.evaluate:
        orchestrator.evaluator.evaluate_all_regions(regions=target_regions)

    if args.generate:
        orchestrator.writer.sync_vault_and_letters(compile_pdf=not args.no_compile)

if __name__ == "__main__":
    main()
