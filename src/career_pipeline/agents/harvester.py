"""
career_pipeline.agents.harvester - Subagent 1: Job Harvester
Executes multi-ATS board scraping, search engine queries, and email alert ingestion.
Deduplicates and stores raw postings in SQLite.
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..storage.db import init_db, is_seen, upsert_posting, compute_job_id
from ..scrapers.ats_clients import (
    GreenhouseClient, LeverClient, PersonioClient, AshbyClient, WorkdayClient,
    RecruiteeClient, TeamtailorClient, SmartRecruitersClient, SuccessFactorsClient,
    AvatureClient, MQVClient, TopticaClient, MTUClient, SerpApiClient
)
from ..integrations.email_inbox import process_inbox_directory

class JobHarvesterSubagent:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        init_db(self.db_path)

    def crawl_all(self, companies_path: Optional[Path] = None, inbox_dir: Optional[Path] = None, serpapi_key: Optional[str] = None, verbose: bool = True) -> Dict[str, Any]:
        """Runs full discovery across ATS boards, email inbox, and Google Jobs."""
        new_jobs = 0

        # 1. Company ATS boards
        if companies_path and companies_path.exists():
            if verbose:
                print("  [Harvester] Crawling corporate ATS boards...")
            try:
                companies_data = json.loads(companies_path.read_text(encoding="utf-8"))
                for comp in companies_data.get("companies", []):
                    if not comp.get("enabled", True):
                        continue
                    ats_type = comp.get("ats_type", "").lower()
                    ats_id = comp.get("ats_id", "")
                    ats_config = comp.get("ats_config", {})
                    name = comp["name"]
                    loc_filter = comp.get("location_filter", ["Munich", "Berlin", "Remote", "Germany"])
                    postings = []

                    try:
                        if ats_type == "greenhouse":
                            postings = GreenhouseClient.fetch_jobs(ats_id, name, loc_filter)
                        elif ats_type == "lever":
                            postings = LeverClient.fetch_jobs(ats_id, name, loc_filter)
                        elif ats_type == "personio":
                            postings = PersonioClient.fetch_jobs(ats_id, name, loc_filter)
                        elif ats_type == "ashby":
                            postings = AshbyClient.fetch_jobs(ats_id, name, loc_filter)
                        elif ats_type == "workday":
                            postings = WorkdayClient.fetch_jobs(ats_config, name, loc_filter)
                        elif ats_type == "recruitee":
                            postings = RecruiteeClient.fetch_jobs(ats_id, name, loc_filter)
                        elif ats_type == "teamtailor":
                            postings = TeamtailorClient.fetch_jobs(ats_id, name, loc_filter)
                        elif ats_type == "smartrecruiters":
                            postings = SmartRecruitersClient.fetch_jobs(ats_id, name, loc_filter)
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
                            if not is_seen(self.db_path, p["canonical_url"]):
                                upsert_posting(self.db_path, p)
                                new_jobs += 1
                                if verbose:
                                    print(f"    [+] Discovered: {p['company']} - {p['title']}")
                    except Exception as e:
                        if verbose:
                            print(f"    [!] Error scraping {comp['name']}: {e}")

                # 2. SerpAPI Search
                eqs = companies_data.get("ecosystem_queries", [])
                if eqs:
                    serp_client = SerpApiClient(api_key=serpapi_key)
                    if serp_client.is_available():
                        if verbose:
                            print(f"  [Harvester] Running live Google Jobs queries via SerpAPI ({len(eqs)} queries)...")
                        for q in eqs:
                            s_jobs = serp_client.search_jobs(q)
                            for sj in s_jobs:
                                if not is_seen(self.db_path, sj["canonical_url"]):
                                    upsert_posting(self.db_path, sj)
                                    new_jobs += 1
                                    if verbose:
                                        print(f"    [+] Discovered (SerpAPI): {sj['company']} - {sj['title']}")
            except Exception as e:
                if verbose:
                    print(f"  [!] Harvester error: {e}")

        # 3. Email alerts
        if inbox_dir and inbox_dir.exists():
            if verbose:
                print("  [Harvester] Parsing email alert inbox...")
            archive_dir = inbox_dir / "Archive"
            postings = process_inbox_directory(inbox_dir, archive_dir)
            for p in postings:
                if not is_seen(self.db_path, p["canonical_url"]):
                    upsert_posting(self.db_path, p)
                    new_jobs += 1
                    if verbose:
                        print(f"    [+] Discovered (Email): {p['company']} - {p['title']}")

        return {
            "total_new": new_jobs
        }
