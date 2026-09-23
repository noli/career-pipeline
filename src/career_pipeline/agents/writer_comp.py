"""
career_pipeline.agents.writer_comp - Subagent 3: Comp & Letter Strategist
Drafts tailored LaTeX cover letters with escaped typography, compiles headless PDFs via Tectonic,
and synchronizes OKF Opportunity notes and regional indices in the Obsidian vault.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
from ..models import CandidatePersona
from ..storage.db import get_db_connection
from ..generator.letter_engine import generate_cover_letter
from ..generator.typography import slugify
from ..integrations.obsidian import generate_vault_opportunity_note, update_vault_opportunities_index

class WriterAndCompSubagent:
    def __init__(self, db_path: Path, persona: CandidatePersona, vault_dir: Optional[Path] = None, template_path: Optional[Path] = None):
        self.db_path = db_path
        self.persona = persona
        self.vault_dir = vault_dir
        self.template_path = template_path

    def sync_vault_and_letters(self, compile_pdf: bool = True) -> Dict[str, Any]:
        """Generates opportunity notes, cover letters, PDFs, and updates regional indices."""
        if not self.vault_dir or not self.vault_dir.exists():
            return {"status": "skipped", "reason": "No vault directory configured"}

        letters_dir = self.vault_dir / "Tailored_Letters"
        pdf_dir = self.vault_dir / "PDFs"
        letters_dir.mkdir(parents=True, exist_ok=True)
        pdf_dir.mkdir(parents=True, exist_ok=True)

        generated_notes = 0
        generated_letters = 0

        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT p.*, e.region, e.fit_score, e.role_archetype, e.matching_pillars,
                       e.key_strengths, e.gaps_risks, e.pitch_strategy, e.compensation_estimate
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
                if isinstance(r.get("compensation_estimate"), str):
                    try:
                        r["compensation_estimate"] = json.loads(r["compensation_estimate"])
                    except Exception:
                        pass

                # Generate or update OKF Opportunity note with regional tag
                generate_vault_opportunity_note(self.vault_dir, r, r, region=r.get("region", "munich"))
                generated_notes += 1

                # Generate LaTeX cover letter and compile PDF if not yet present
                if self.template_path and self.template_path.exists():
                    comp_slug = slugify(r.get("company", ""))
                    title_slug = slugify(r.get("title", ""))[:40]
                    tex_file = letters_dir / f"{comp_slug}_{title_slug}.tex"
                    pdf_file = pdf_dir / f"{comp_slug}_{title_slug}.pdf"

                    if not tex_file.exists() or not pdf_file.exists():
                        generate_cover_letter(
                            posting=r,
                            evaluation=r,
                            persona=self.persona,
                            template_path=self.template_path,
                            output_dir=letters_dir,
                            pdf_dir=pdf_dir,
                            compile_pdf=compile_pdf
                        )
                        generated_letters += 1

        # Rebuild master index.md, Munich.md, and Berlin.md
        update_vault_opportunities_index(self.vault_dir)

        return {
            "status": "success",
            "notes_synced": generated_notes,
            "letters_generated": generated_letters
        }
