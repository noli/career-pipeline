"""
career_pipeline.agents.orchestrator - Central Career Pipeline Orchestrator
Coordinates Harvester, Evaluator, and Writer & Comp Subagents.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..models import CandidatePersona
from .harvester import JobHarvesterSubagent
from .evaluator import FitEvaluatorSubagent
from .writer_comp import WriterAndCompSubagent

class CareerOrchestrator:
    def __init__(
        self,
        db_path: Path,
        persona: CandidatePersona,
        vault_dir: Optional[Path] = None,
        companies_path: Optional[Path] = None,
        template_path: Optional[Path] = None,
        inbox_dir: Optional[Path] = None
    ):
        self.db_path = db_path
        self.persona = persona
        self.vault_dir = vault_dir
        self.companies_path = companies_path or (vault_dir / "Data" / "target_companies.json" if vault_dir else None)
        self.template_path = template_path
        self.inbox_dir = inbox_dir or (vault_dir / "Inbox" if vault_dir else None)

        # Initialize subagents
        self.harvester = JobHarvesterSubagent(db_path=self.db_path)
        self.evaluator = FitEvaluatorSubagent(db_path=self.db_path, persona=self.persona)
        self.writer = WriterAndCompSubagent(
            db_path=self.db_path,
            persona=self.persona,
            vault_dir=self.vault_dir,
            template_path=self.template_path
        )

    def run_full_pipeline(self, regions: Optional[List[str]] = None, compile_pdf: bool = True) -> Dict[str, Any]:
        """Runs end-to-end multi-agent pipeline: Ingestion -> Multi-Region Scoring -> Artifact Generation."""
        print("=== [CareerOrchestrator] Starting Autonomous Multi-Agent Pipeline ===")
        active_regions = regions or list(self.persona.regions.keys()) or ["munich", "berlin"]

        # 1. Ingestion Subagent
        print(f"\nStep 1: Spawning Harvester Subagent...")
        crawl_res = self.harvester.crawl_all(
            companies_path=self.companies_path,
            inbox_dir=self.inbox_dir
        )
        print(f"  [Harvester Complete] Discovered {crawl_res[total_new]} new postings.")

        # 2. Fit Evaluator Subagent
        print(f"\nStep 2: Spawning Fit Evaluator Subagent across regions: {active_regions}...")
        eval_res = self.evaluator.evaluate_all_regions(regions=active_regions)

        # 3. Writer & Compensation Subagent
        print(f"\nStep 3: Spawning Comp & Writer Subagent...")
        write_res = self.writer.sync_vault_and_letters(compile_pdf=compile_pdf)
        print(f"  [Writer Complete] Synced {write_res.get(notes_synced, 0)} notes and {write_res.get(letters_generated, 0)} letters.")

        print(f"\n=== [CareerOrchestrator] Autonomous Pipeline Completed Successfully ===")
        return {
            "crawl": crawl_res,
            "evaluations": eval_res,
            "vault_sync": write_res
        }
