"""
career_pipeline.config - Configuration & Environment Loader
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from .models import CandidatePersona

DEFAULT_CONFIG = {
    "database_path": "data/jobs.db",
    "target_companies_path": "configs/target_companies.json",
    "persona_path": "configs/persona.yaml",
    "output_dir": "output",
    "high_match_threshold": 85,
    "digest_min_threshold": 70,
    "digest_max_threshold": 84,
    "compile_pdfs": True
}

def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def load_persona(persona_path: Path) -> CandidatePersona:
    """Loads CandidatePersona from YAML file."""
    data = load_yaml(persona_path)
    contact = data.get("contact", {})
    prefs = data.get("preferences", {})
    
    first_name = contact.get("first_name") or contact.get("name", "Candidate").split()[0]
    last_name = contact.get("last_name") or (" ".join(contact.get("name", "").split()[1:]) if " " in contact.get("name", "") else "")

    return CandidatePersona(
        name=contact.get("name", "Candidate"),
        first_name=first_name,
        last_name=last_name,
        title=contact.get("title", "Technical Lead"),
        address_line1=contact.get("address_line1", ""),
        address_line2=contact.get("address_line2", ""),
        phone=contact.get("phone", ""),
        email=contact.get("email", ""),
        linkedin=contact.get("linkedin", ""),
        github=contact.get("github", ""),
        target_locations=prefs.get("target_locations", ["munich", "remote", "germany"]),
        excluded_locations=prefs.get("excluded_locations", []),
        dealbreaker_keywords=prefs.get("dealbreaker_keywords", []),
        pillars=data.get("pillars", []),
        narratives=data.get("narratives", {})
    )
