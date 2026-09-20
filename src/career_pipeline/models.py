"""
career_pipeline.models - Typed Domain Models
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class Posting:
    id: str
    canonical_url: str
    company: str
    title: str
    location: str = ""
    workplace_type: str = ""
    department: str = ""
    ats_source: str = ""
    raw_content: str = ""
    content_hash: str = ""
    discovered_at: str = ""
    posted_at: Optional[str] = None
    status: str = "new"

@dataclass
class Evaluation:
    posting_id: str
    fit_score: int
    role_archetype: str
    seniority: str
    technical_alignment: int
    seniority_impact: int
    location_commute: int
    company_mission: int
    comp_potential: int
    matching_pillars: List[str] = field(default_factory=list)
    key_strengths: List[str] = field(default_factory=list)
    gaps_risks: List[str] = field(default_factory=list)
    pitch_strategy: str = ""

@dataclass
class CandidatePersona:
    name: str = "Candidate"
    first_name: str = "Candidate"
    last_name: str = ""
    title: str = "Technical Lead"
    address_line1: str = ""
    address_line2: str = ""
    phone: str = ""
    email: str = ""
    linkedin: str = ""
    github: str = ""
    target_locations: List[str] = field(default_factory=list)
    excluded_locations: List[str] = field(default_factory=list)
    dealbreaker_keywords: List[str] = field(default_factory=list)
    pillars: List[Dict[str, Any]] = field(default_factory=list)
    narratives: Dict[str, Dict[str, str]] = field(default_factory=dict)
