"""
career_pipeline.evaluator.matcher - Configurable Persona-Based Job Matching Engine
Evaluates job postings dynamically against a CandidatePersona.
Calculates weighted match scores (0-100), extracts pitch strengths, and flags gap risks.
"""
import re
from typing import Dict, Any, List, Tuple
from ..models import CandidatePersona, Evaluation

DEFAULT_JUNIOR_KEYWORDS = [
    "junior", "graduate program", "trainee", "working student", 
    "werkstudent", "praktikum", "internship", "intern", "entry level", "entry-level"
]

DEFAULT_NON_TECH_KEYWORDS = [
    "scrum master", "agile coach", "office manager", "executive assistant", 
    "hr manager", "human resources", "recruiter", "recruiting", "talent acquisition",
    "accountant", "accounting", "payroll", "sales representative", "account executive",
    "receptionist", "facility manager"
]

def evaluate_job(posting: Dict[str, Any], persona: CandidatePersona) -> Dict[str, Any]:
    """
    Evaluates a normalized job posting against the given CandidatePersona.
    Returns a comprehensive evaluation dictionary.
    """
    title = posting.get("title", "").lower()
    raw_content = posting.get("raw_content", "").lower()
    full_text = f"{title} {raw_content}"
    location = posting.get("location", "").lower()
    company = posting.get("company", "")

    dealbreakers = []
    
    # 1. Junior / Non-tech check
    all_dealbreakers = list(persona.dealbreaker_keywords) or (DEFAULT_JUNIOR_KEYWORDS + DEFAULT_NON_TECH_KEYWORDS)
    if any(re.search(r"\b" + re.escape(jk) + r"\b", title) for jk in all_dealbreakers):
        dealbreakers.append("Junior, administrative, or non-technical role title")

    # 2. Location Filtering
    excluded_locs = persona.excluded_locations or []
    target_locs = persona.target_locations or ["munich", "remote", "germany"]
    
    is_remote = "100% remote" in full_text or "fully remote" in full_text or (
        ("remote" in location or posting.get("workplace_type") == "remote") 
        and not any(re.search(r"\b" + re.escape(fl) + r"\b", location) for fl in excluded_locs)
    )
    is_target_commute = any(mt in location for mt in target_locs)
    is_explicit_outside = any(
        re.search(r"\b" + re.escape(fl) + r"\b", location) or re.search(r"\b" + re.escape(fl) + r"\b", title) 
        for fl in excluded_locs
    )

    if is_explicit_outside and not is_target_commute and not ("remote" in title):
        dealbreakers.append(f"Requires physical relocation outside target area ({location or title})")

    # 3. Seniority & Impact Scoring (max 25)
    seniority_impact = 0
    seniority_label = "Senior"
    
    if any(kw in title for kw in [
        "head of", "director", "chief engineer", "vice president", "vp", 
        "group lead", "team lead", "engineering lead", "technical lead", "tech lead",
        "engineering manager", "partner", "associate partner", "senior manager"
    ]):
        seniority_impact = 25
        seniority_label = "Lead / Executive"
    elif any(kw in title for kw in [
        "principal", "staff", "technical lead manager", "tlm", "lead ", "architect",
        "managing consultant", "senior consultant"
    ]):
        seniority_impact = 22
        seniority_label = "Principal / Staff"
    elif any(kw in title for kw in ["senior", "expert", "specialist", "consultant"]):
        seniority_impact = 18
        seniority_label = "Senior"
    else:
        seniority_impact = 12
        seniority_label = "Mid-Level"

    # 4. Dynamic Pillar & Keyword Scoring (max 35)
    tech_score = 0
    matching_pillars = []
    
    for pillar in persona.pillars:
        p_name = pillar.get("name", "Technical Expertise")
        p_keywords = pillar.get("keywords", [])
        p_weight = pillar.get("weight", 15)
        
        matches = [kw for kw in p_keywords if kw in full_text]
        if matches:
            matching_pillars.append(p_name)
            tech_score += min(p_weight, len(matches) * 5)

    tech_score = min(40, tech_score)

    # 5. Location / Commute Score (max 20)
    loc_score = 0
    if is_remote:
        loc_score = 20
    elif is_target_commute:
        loc_score = 20
    elif not is_explicit_outside:
        loc_score = 12
    else:
        loc_score = 0

    # 6. Mission & Deep-Tech Affinity (max 20)
    mission_score = 15

    # Total Score Calculation
    raw_score = seniority_impact + tech_score + loc_score + mission_score
    if dealbreakers:
        fit_score = min(40, max(15, raw_score - 50))
    else:
        fit_score = min(100, max(30, raw_score))

    # Archetype derivation
    if matching_pillars:
        archetype = matching_pillars[0]
    else:
        archetype = "Engineering Leadership"

    # Strengths and Gaps
    key_strengths = [
        f"Matches {len(matching_pillars)} core expertise pillars: {', '.join(matching_pillars[:2])}",
        f"Seniority alignment: {seniority_label} level scope",
        f"Geographic / Work-mode fit: {'Remote / Hybrid' if is_remote else 'Target Location'}"
    ]

    return {
        "posting_id": posting.get("id", ""),
        "fit_score": fit_score,
        "role_archetype": archetype,
        "seniority": seniority_label,
        "technical_alignment": tech_score,
        "seniority_impact": seniority_impact,
        "location_commute": loc_score,
        "company_mission": mission_score,
        "comp_potential": 15,
        "matching_pillars": matching_pillars,
        "key_strengths": key_strengths,
        "gaps_risks": dealbreakers,
        "pitch_strategy": f"Align expertise in {archetype} with {company}'s strategic mission."
    }
