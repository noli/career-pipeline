"""
career_pipeline.generator.letter_engine - Modular LaTeX Cover Letter Generator
Renders clean, parameterized LaTeX cover letters via Jinja2 with zero personal spillage.
"""
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader

from ..models import CandidatePersona
from .typography import slugify, latex_escape
from .tectonic import compile_tex_to_pdf

def get_jinja_env(template_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        variable_start_string="<<",
        variable_end_string=">>",
        block_start_string="<%",
        block_end_string="%>",
        autoescape=False
    )

def generate_cover_letter(
    posting: Dict[str, Any],
    evaluation: Dict[str, Any],
    persona: CandidatePersona,
    template_path: Path,
    output_dir: Path,
    compile_pdf: bool = True
) -> Dict[str, Any]:
    """
    Generates a tailored LaTeX cover letter (.tex) and optionally compiles PDF.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    env = get_jinja_env(template_path.parent)
    template = env.get_template(template_path.name)

    company = posting.get("company", "Company")
    title = posting.get("title", "Role")
    location = posting.get("location", "Munich, Germany")

    safe_company = latex_escape(company)
    safe_title = latex_escape(title)
    safe_location = latex_escape(location)

    comp_slug = slugify(company)
    title_slug = slugify(title)[:40]
    tex_filename = f"{comp_slug}_{title_slug}.tex"
    pdf_filename = f"{comp_slug}_{title_slug}.pdf"
    tex_path = output_dir / tex_filename

    # Narrative extraction from persona
    narratives = persona.narratives.get("default", {})
    p1 = f"I am writing to express my enthusiastic interest in the \\textbf{{{safe_title}}} position at {safe_company}. " + narratives.get(
        "hook", "As an experienced technical leader, I bring a proven record of engineering excellence."
    )
    p2 = narratives.get(
        "experience", "Throughout my career, I have specialized in architecting and delivering mission-critical systems."
    )
    p3 = narratives.get(
        "mitigation", "I pair deep technical grounding with rapid learning velocity, adopting unfamiliar domains quickly."
    )
    p4 = narratives.get(
        "closing", f"I have followed {safe_company}'s trajectory with great admiration and look forward to discussing how my background aligns with your team."
    )

    rendered_tex = template.render(
        candidate_name=persona.name,
        candidate_first_name=persona.first_name,
        candidate_last_name=persona.last_name,
        candidate_title=persona.title,
        candidate_address_line1=persona.address_line1,
        candidate_address_line2=persona.address_line2,
        candidate_phone=persona.phone,
        candidate_email=persona.email,
        safe_company=safe_company,
        safe_title=safe_title,
        safe_location=safe_location,
        letter_date=datetime.now().strftime("%B %d, %Y"),
        paragraph_1=p1,
        paragraph_2=p2,
        paragraph_3=p3,
        paragraph_4=p4
    )

    tex_path.write_text(rendered_tex, encoding="utf-8")

    pdf_compiled = False
    if compile_pdf:
        pdf_compiled = compile_tex_to_pdf(tex_path, output_dir)

    return {
        "tex_path": tex_path,
        "pdf_path": output_dir / pdf_filename if pdf_compiled else None,
        "tex_filename": tex_filename,
        "pdf_filename": pdf_filename if pdf_compiled else None
    }
