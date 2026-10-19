"""
career_pipeline.generator.letter_engine - Dynamic LaTeX Cover Letter Generator
Renders grounded, highly tailored, human-sounding LaTeX cover letters via Jinja2.
Arguing candidate profile suitability against specific job requirements,
constructively addressing domain gaps, and weaving in core technical passions:
- optics and optical design (love it)
- complex autonomous systems (intrigued)
- managing versatile teams on technical challenges
"""
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
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

def classify_role_domain(title: str, company: str, raw_content: str, archetype: str) -> Tuple[str, Dict[str, bool]]:
    """
    Accurately classifies the primary technical domain of a role
    to select the best-matching narrative and suitability arguments.
    """
    t = title.lower()
    c = company.lower()
    desc = raw_content.lower()

    is_optics = any(k in t for k in [
        "optic", "optical", "laser", "photonics", "lens", "beam", "optomechanic"
    ]) or (
        any(k in desc for k in ["optical design", "free-space optics", "laser communication", "interferomet", "photonics"])
        and not any(k in t for k in ["recruiter", "sales", "hr"])
    )

    is_space = any(k in c for k in [
        "mynaric", "iceye", "isar aerospace", "the exploration company", "ohb", "ororatech"
    ]) or any(k in t for k in [
        "satellite", "payload", "orbital", "in-orbit", "spacecraft", "propulsion", "satcom", "flight dynamics"
    ])

    is_enterprise = any(k in c for k in [
        "celonis", "deloitte", "roland berger", "mckinsey", "bcg"
    ]) or any(k in t for k in [
        "value engineering", "value consulting", "business transformation", "enterprise architect", "process intelligence"
    ])

    is_quantum = any(k in c for k in [
        "planqc", "iqm", "quantumdiamonds", "q.ant", "kiutra"
    ]) or any(k in t for k in [
        "quantum", "qubit", "cryogenic", "ion trap"
    ])

    is_robotics_autonomy = any(k in t for k in [
        "autonomy", "autonomous", "lidar", "radar", "perception", "robotics",
        "sensor fusion", "point cloud", "adas", "ugv", "uav", "c-uas", "motion planning"
    ]) or any(k in c for k in [
        "quantum-systems", "navvis", "agile robots", "magazino", "fernride"
    ])

    is_hardware_ee = any(k in t for k in [
        "e/e", "electronics", "emc", "compliance", "pcb", "hardware", "silicon", "pmic", "semiconductor", "electrical"
    ])

    is_management = any(k in t for k in [
        "lead", "head", "director", "manager", "chief", "vp", "tpm", "program manager", "project manager", "team lead"
    ])

    # Determine primary domain
    if is_optics:
        primary = "optics"
    elif is_enterprise:
        primary = "enterprise"
    elif is_quantum:
        primary = "quantum"
    elif is_space and not is_robotics_autonomy:
        primary = "space"
    elif is_robotics_autonomy:
        primary = "autonomy"
    elif is_hardware_ee:
        primary = "hardware"
    elif is_management:
        primary = "management"
    else:
        primary = "general_tech"

    facets = {
        "has_optics": is_optics,
        "has_space": is_space,
        "has_enterprise": is_enterprise,
        "has_quantum": is_quantum,
        "has_autonomy": is_robotics_autonomy,
        "has_hardware": is_hardware_ee,
        "has_management": is_management
    }
    return primary, facets

def compose_tailored_letter_paragraphs(
    posting: Dict[str, Any],
    evaluation: Dict[str, Any],
    persona: CandidatePersona
) -> Tuple[str, str, str, str]:
    """
    Constructs a 4-paragraph, highly tailored, authentic cover letter:
    1. Grounded opening & explicit interest anchor (no blooming hype).
    2. Suitability argument: Profile details vs. Position requirements.
    3. Constructive gap addressing & commitment to rapid first-principles ramp-up.
    4. Direct, professional closing.
    """
    title = posting.get("title", "Role")
    company = posting.get("company", "Company")
    raw_content = posting.get("raw_content", "")
    archetype = evaluation.get("role_archetype", "")

    safe_title = latex_escape(title)
    safe_company = latex_escape(company)

    primary_domain, facets = classify_role_domain(title, company, raw_content, archetype)

    # Base opening sentence
    p1_open = (
        f"I am writing to apply for the \\textbf{{{safe_title}}} position at {safe_company}. "
        "With a background encompassing doctoral research in experimental physics at Humboldt University in Berlin "
        "and research at UC Berkeley, followed by leading the series development of automotive LIDAR sensors at BMW Group "
        "and OSRAM, my work has centered on turning complex physical and electronic concepts into reliable, production hardware."
    )

    # --- Paragraph 1: Tailored Interest Anchor ---
    if primary_domain == "optics":
        p1_interest = (
            "Optics and optical design are disciplines I genuinely love---from the precision alignment of free-space laser "
            "setups during my research to the thermal, optomechanical, and optical frontend validation of series automotive sensors."
        )
    elif primary_domain in ("autonomy", "hardware"):
        p1_interest = (
            "I have long been intrigued by the engineering challenges of complex autonomous systems---particularly the interplay "
            "between raw physical sensor limitations, harsh environmental operating envelopes, and fail-operational real-time perception."
        )
    elif primary_domain == "quantum":
        p1_interest = (
            "Having conducted doctoral research in quantum optics and experimental physics at Humboldt University and UC Berkeley, "
            "advancing novel physical systems from laboratory prototypes into industrialized hardware is work I care about deeply."
        )
    elif primary_domain == "space":
        p1_interest = (
            "I have long been intrigued by complex autonomous and aerospace systems---particularly the design of mission-critical hardware "
            "that must operate reliably in extreme environments where in-field maintenance is impossible."
        )
    else:  # enterprise, management, general_tech
        p1_interest = (
            "A central driver in my career is managing versatile teams on demanding technical challenges---fostering alignment across "
            "engineering, product, and leadership stakeholders to translate complex requirements into measurable operational success."
        )

    paragraph_1 = f"{p1_open} {p1_interest}"

    # --- Paragraph 2: Suitability Argument (Profile vs Position Requirements) ---
    if primary_domain == "optics":
        p2 = (
            f"The technical scope of the {safe_title} role at {safe_company} directly aligns with my hands-on systems experience. "
            "In my work at BMW Group and OSRAM, I served as technical lead and Chief Engineer for series LIDAR, responsible for "
            "optical frontend design, beam propagation, thermal drift mitigation across broad automotive operating temperatures, "
            "and automated lens cleaning and blockage detection. During my research at UC Berkeley and leading photonic research institutes, "
            "I designed ultra-high vacuum chambers and frequency-stabilized laser setups for quantum optical systems. Whether conducting optical "
            "simulations or debugging optomechanical alignment tolerances on the test bench, I combine first-principles optical physics "
            "with rigorous laboratory verification to deliver stable, high-performance designs."
        )
    elif primary_domain == "autonomy":
        p2 = (
            f"My background directly addresses the core requirements for the {safe_title} position. As Chief Engineer and E/E Team Lead "
            "for the world-first Level 3 series LIDAR on the BMW 7 Series, I led the full sensor lifecycle from initial architecture through "
            "to series vehicle integration. This included designing high-resolution point-cloud signal processing pipelines, managing "
            "multi-modal sensor fusion trade-offs, and enforcing ISO 26262 functional safety and fail-operational architectures. I am deeply "
            "accustomed to diagnosing real-world sensor anomalies and working at the boundary between raw physical signals and autonomous "
            "perception algorithms."
        )
    elif primary_domain == "quantum":
        p2 = (
            f"The mission of {safe_company} connects directly to my experimental grounding in quantum hardware. At UC Berkeley, I designed, "
            "assembled, and achieved ultra-high vacuum in an ion-trap testing apparatus and engineered laser stabilization systems for single-particle "
            "trapping. Later at OSRAM and BMW Group, I expanded this foundation into industrial-grade systems engineering: managing multi-tier "
            "supplier networks, establishing precision optical test benches, and implementing rigorous defect management. I bring a rare combination "
            "of first-principles quantum physical intuition and disciplined series product delivery."
        )
    elif primary_domain == "space":
        p2 = (
            f"The operational demands of {safe_company}'s flight systems closely parallel the reliability standards I have enforced throughout "
            "my career. In my series development leadership at BMW and OSRAM, I governed the qualification of precision optoelectronic "
            "sensor hardware subjected to severe thermal cycling, shock, and vibration profiles where in-field intervention is impossible. "
            "During my experimental research at UC Berkeley, I built custom vacuum instrumentation and laser stabilization hardware from scratch. "
            "I bridge deep physics understanding with disciplined systems engineering to ensure payload and instrumentation integrity."
        )
    elif primary_domain == "enterprise":
        p2 = (
            f"The requirements for the {safe_title} role at {safe_company} match my experience connecting first-principles physical science with "
            "executive delivery in complex organizations. Managing deep-tech series development at BMW required navigating complex supplier ecosystems, "
            "conducting rigorous technical due diligence, and translating physical engineering trade-offs into executive roadmap decisions. To enhance "
            "operational throughput, I built and deployed custom Python-based Agentic AI pipelines that streamlined engineering specification reviews across departmental silos."
        )
    elif primary_domain == "hardware":
        p2 = (
            f"Throughout my engineering career, my core strength has been translating complex physical and architectural requirements into qualified hardware. "
            "At BMW Group, I governed electrical and electronic sensor architectures through PCB bring-up, power integrity assessments, and 100\\% EMC "
            "compliance testing under harsh automotive constraints. I bridge the gap between low-level electronic hardware constraints and "
            "system-level validation, ensuring that designs meet stringent durability and reliability standards."
        )
    else:  # management, general_tech
        p2 = (
            "Leading technical programs has reinforced my player-coach approach: guiding multidisciplinary teams of optical, electrical, "
            "mechanical, and embedded software engineers toward unified system goals. At BMW Group, I managed multi-tier build matrices "
            "from concept schematics through board bring-up, DFM/DFA, and supplier qualification into mass vehicle production. I distill "
            "complex physical and architectural constraints into clear, actionable program decisions, while actively building software tooling---such "
            "as custom Python-based Agentic AI workflows---to automate specification tracking and accelerate review cycles."
        )

    paragraph_2 = p2

    # --- Paragraph 3: Constructive Gap Addressing & Fast Learning ---
    if facets.get("has_space") and primary_domain == "optics":
        p3 = (
            "While my recent series industrialization track record has been in automotive Tier-1/OEM environments rather than orbital space-flight hardware, "
            "the underlying physical requirements---sub-microradian optical alignment, thermal drift mitigation in vacuum or sealed structures, and uncompromising "
            "hardware reliability---are fundamentally aligned. I approach unfamiliar standards with an eager, disciplined learning mindset, and I welcome the "
            "challenge of rapidly mastering space-qualification protocols (such as ECSS standards) to contribute directly to your flight programs. Furthermore, "
            "managing versatile teams on technical challenges remains one of the most rewarding aspects of my work: I thrive when working alongside mechanical, "
            "electrical, and firmware engineers to deliver unified, robust hardware."
        )
    elif primary_domain == "enterprise":
        p3 = (
            "Coming from safety-critical physical systems, my core advantage is understanding how abstract data models map to real-world operational bottlenecks. "
            "While enterprise software platforms differ in toolchain from embedded hardware architectures, the systems engineering mindset---identifying root causes, "
            "eliminating pipeline friction, and driving data-backed decisions---is shared. I am eager to expand my focus into enterprise process transformation and actively "
            "ramp up on your domain-specific methodologies, while continuing to leverage my passion for managing versatile teams through complex cross-functional challenges."
        )
    elif primary_domain in ("autonomy", "hardware") and not facets.get("has_optics"):
        p3 = (
            "While specific hardware architectures and operational platforms evolve rapidly, my core advantage is a first-principles grasp of underlying "
            "physical and electrical constraints. I am constantly expanding my knowledge in modern simulation tools and automated validation suites, "
            "and I welcome the opportunity to dive into any platform-specific frameworks your team uses. Managing versatile teams on technical "
            "challenges has shown me that combining deep technical curiosity with structured systems engineering is the most effective way to turn "
            "ambitious concepts into dependable, field-ready systems."
        )
    elif facets.get("has_space"):
        p3 = (
            "While my recent series production experience has been in commercial automotive platforms under ISO 26262, the mission-critical demand for fail-operational "
            "hardware under extreme environments is identical in space architectures. I approach domain-specific qualification with intellectual curiosity and rigorous "
            "discipline, eager to master aerospace standards rapidly. Furthermore, managing versatile teams on technical challenges remains central to my work: "
            "I enjoy fostering a collaborative culture that solves hard cross-disciplinary roadblocks."
        )
    else:
        p3 = (
            "Where specific internal tools or domain frameworks diverge from my immediate toolchain, I rely on strong first-principles thinking and steep learning curves. "
            "Throughout my transitions between academic quantum research, OSRAM optics, and BMW automotive industrialization, I have consistently demonstrated the ability "
            "to assimilate new technical domains quickly and deliver measurable results. Managing versatile teams on technical challenges remains central to my work, "
            "and I enjoy fostering a collaborative culture that solves hard engineering roadblocks."
        )

    paragraph_3 = p3

    # --- Paragraph 4: Grounded, Professional Closing ---
    domain_ref = "optical systems" if primary_domain == "optics" else (
        "autonomous systems" if primary_domain == "autonomy" else (
            "quantum hardware" if primary_domain == "quantum" else (
                "space systems" if primary_domain == "space" else (
                    "enterprise systems" if primary_domain == "enterprise" else "hardware engineering"
                )
            )
        )
    )
    paragraph_4 = (
        f"I would welcome the opportunity to discuss how my background in {domain_ref} and hands-on engineering approach can support "
        f"{safe_company}'s technical roadmap. Thank you for your time and consideration."
    )

    return paragraph_1, paragraph_2, paragraph_3, paragraph_4

def generate_cover_letter(
    posting: Dict[str, Any],
    evaluation: Dict[str, Any],
    persona: CandidatePersona,
    template_path: Path,
    output_dir: Path,
    pdf_dir: Optional[Path] = None,
    compile_pdf: bool = True,
    force: bool = False
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
    target_pdf_dir = pdf_dir or output_dir
    pdf_path = target_pdf_dir / pdf_filename

    if tex_path.exists() and pdf_path.exists() and not force:
        return {
            "tex_path": tex_path,
            "pdf_path": pdf_path,
            "tex_filename": tex_filename,
            "pdf_filename": pdf_filename,
            "skipped": True
        }

    p1, p2, p3, p4 = compose_tailored_letter_paragraphs(posting, evaluation, persona)

    rendered_tex = template.render(
        candidate_name=latex_escape(persona.name),
        candidate_first_name=latex_escape(persona.first_name),
        candidate_last_name=latex_escape(persona.last_name),
        candidate_title=latex_escape(persona.title),
        candidate_address_line1=latex_escape(persona.address_line1),
        candidate_address_line2=latex_escape(persona.address_line2),
        candidate_phone=latex_escape(persona.phone),
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
        pdf_compiled = compile_tex_to_pdf(tex_path, target_pdf_dir)

    return {
        "tex_path": tex_path,
        "pdf_path": target_pdf_dir / pdf_filename if pdf_compiled else None,
        "tex_filename": tex_filename,
        "pdf_filename": pdf_filename if pdf_compiled else None,
        "skipped": False
    }
