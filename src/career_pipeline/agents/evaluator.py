"""
career_pipeline.agents.evaluator - Subagent 2: Fit Evaluator
Evaluates postings in parallel across configured regions (e.g. Munich & Berlin).
Computes weighted pillar alignment, seniority impact, and attaches compensation estimates.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..models import CandidatePersona
from ..storage.db import get_unscored_postings, save_evaluation
from ..evaluator.matcher import evaluate_job

class FitEvaluatorSubagent:
    def __init__(self, db_path: Path, persona: CandidatePersona):
        self.db_path = db_path
        self.persona = persona

    def evaluate_region(self, region: str = "munich") -> Dict[str, Any]:
        """Evaluates all unscored postings for a specific region."""
        unscored = get_unscored_postings(self.db_path, region=region)
        high_fit = []
        pot_fit = []

        for p in unscored:
            eval_res = evaluate_job(p, self.persona, region=region)
            save_evaluation(self.db_path, eval_res, region=region)
            
            score = eval_res.get("fit_score", 0)
            if score >= 85:
                high_fit.append({**p, **eval_res})
                print(f"    [Match {score}% | {region.title()}] {p['company']} - {p['title']} ({eval_res['role_archetype']})")
            elif score >= 70:
                pot_fit.append({**p, **eval_res})

        return {
            "region": region,
            "evaluated_count": len(unscored),
            "high_fit_count": len(high_fit),
            "high_fit_roles": high_fit,
            "potential_fit_count": len(pot_fit)
        }

    def evaluate_all_regions(self, regions: Optional[List[str]] = None) -> Dict[str, Any]:
        """Evaluates postings across all specified regions."""
        regs = regions or list(self.persona.regions.keys()) or ["munich", "berlin"]
        results = {}
        for r in regs:
            print(f"  [Evaluator] Scoring postings for region: {r.upper()}...")
            results[r] = self.evaluate_region(r)
        return results
