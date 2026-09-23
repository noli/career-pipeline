"""
career_pipeline.evaluator.compensation - Predictive Compensation & Salary Modeling Engine
Estimates base salary bands, expected bonus, equity/LTI instruments, and total target compensation
calibrated against Munich and Berlin deep-tech market benchmarks.
"""
import re
from typing import Dict, Any, Optional

TIER1_US_TECH = {"apple", "google", "nvidia", "amazon", "qualcomm", "meta", "microsoft"}
STRATEGY_CONSULTING = {"mckinsey", "bcg", "boston consulting group", "roland berger", "porsche consulting", "bain"}
GERMAN_ENTERPRISE = {"siemens", "airbus", "rohde & schwarz", "hensoldt", "mtu aero engines", "knorr-bremse", "bmw", "infineon", "zeiss"}
DEEPTECH_SCALEUPS = {"planqc", "proxima fusion", "helsing", "iqm", "quantum-systems", "celonis", "navvis", "the exploration company", "toptica photonics", "iceye", "marvel fusion", "agile robots", "quantumdiamonds", "kiutra"}

def estimate_compensation(posting: Dict[str, Any], evaluation: Dict[str, Any], region: str = "munich") -> Dict[str, Any]:
    """
    Estimates market compensation bracket for a evaluated position.
    """
    company_raw = posting.get("company", "").lower().strip()
    seniority = evaluation.get("seniority", "Senior")
    fit_score = evaluation.get("fit_score", 85)
    title = posting.get("title", "").lower()

    # 1. Base Salary by Seniority Tier (Munich Baseline)
    if seniority == "Lead / Executive":
        base_min, base_max = 145000, 175000
        bonus_pct = 0.20
    elif seniority == "Principal / Staff":
        base_min, base_max = 135000, 155000
        bonus_pct = 0.18
    elif seniority == "Senior":
        base_min, base_max = 120000, 138000
        bonus_pct = 0.15
    else:
        base_min, base_max = 100000, 118000
        bonus_pct = 0.10

    # 2. Company Segment Adjustments
    equity_type = "None"
    equity_annual_est = 0
    company_profile = "Mid-Market / SME"

    if any(tech in company_raw for tech in TIER1_US_TECH):
        company_profile = "Tier-1 US Tech / Silicon"
        base_min += 15000
        base_max += 20000
        bonus_pct = 0.20
        equity_type = "RSUs / GSUs (Public Liquid Stock)"
        equity_annual_est = 35000 if seniority != "Lead / Executive" else 55000
    elif any(cons in company_raw for cons in STRATEGY_CONSULTING):
        company_profile = "Tier-1 Strategy & Management Consulting"
        base_min += 10000
        base_max += 15000
        bonus_pct = 0.25
        equity_type = "Profit Sharing / Partnership Track"
    elif any(ent in company_raw for ent in GERMAN_ENTERPRISE):
        company_profile = "Major German Industrial Conglomerate (AT / Tariff)"
        base_min += 5000
        base_max += 8000
        bonus_pct = 0.18
        equity_type = "Employee Share Purchase / Corporate Pension"
    elif any(sc in company_raw for sc in DEEPTECH_SCALEUPS):
        company_profile = "Venture-Backed Deep-Tech Scale-Up"
        bonus_pct = 0.15
        equity_type = "Stock Options (VSOP / ESOP 0.1% - 0.5%)"
        equity_annual_est = 15000

    # 3. Regional Cost-of-Living & Market Delta
    reg = (region or "munich").lower()
    if reg == "berlin":
        # Berlin base is traditionally ~8% lower for local roles, but matched for elite deep-tech/AI
        reg_factor = 0.94 if company_profile != "Tier-1 US Tech / Silicon" else 1.0
        base_min = int(base_min * reg_factor)
        base_max = int(base_max * reg_factor)
        reg_note = "Berlin tech ecosystem benchmark (~6-8% baseline adjustment, balanced by equity or remote flexibility)."
    else:
        reg_note = "Munich high-tech hub premium (aligned with target €160k - €190k+ package)."

    # 4. Total Target Compensation
    target_bonus_min = int(base_min * bonus_pct)
    target_bonus_max = int(base_max * bonus_pct)
    total_min = base_min + target_bonus_min + equity_annual_est
    total_max = base_max + target_bonus_max + equity_annual_est

    # 5. Negotiation Guidance
    strat = f"Anchor negotiation around €{base_max // 1000}k EUR base with a {int(bonus_pct * 100)}% target bonus. Highlight Ph.D. in experimental physics and decade-long systems delivery track record."

    return {
        "base_salary_min": base_min,
        "base_salary_max": base_max,
        "bonus_pct": bonus_pct,
        "bonus_target_min": target_bonus_min,
        "bonus_target_max": target_bonus_max,
        "equity_type": equity_type,
        "total_comp_min": total_min,
        "total_comp_max": total_max,
        "currency": "EUR",
        "company_profile": company_profile,
        "regional_note": reg_note,
        "negotiation_strategy": strat
    }
