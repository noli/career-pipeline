"""
career_pipeline.storage.db - SQLite Persistence & Deduplication Layer
Safe concurrency using context managers to prevent file-locking issues on Windows.
Supports composite primary keys (posting_id, region) for parallel multi-region ranking.
"""
import sqlite3
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

def get_db_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Path):
    """Initializes or migrates the database schema to support multi-region evaluations."""
    with get_db_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS postings (
                id TEXT PRIMARY KEY,
                canonical_url TEXT UNIQUE,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT,
                workplace_type TEXT,
                department TEXT,
                ats_source TEXT,
                raw_content TEXT,
                content_hash TEXT,
                discovered_at TEXT NOT NULL,
                posted_at TEXT,
                status TEXT NOT NULL DEFAULT 'new'
            );
        """)

        # Check if evaluations table needs migration to composite (posting_id, region)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evaluations'")
        table_exists = cur.fetchone() is not None

        needs_migration = False
        if table_exists:
            cur.execute("PRAGMA table_info(evaluations)")
            cols = {row[1]: row for row in cur.fetchall()}
            if "region" not in cols or cols["region"][5] == 0:
                needs_migration = True

        if needs_migration:
            conn.execute("""
                CREATE TABLE evaluations_new (
                    posting_id TEXT REFERENCES postings(id) ON DELETE CASCADE,
                    region TEXT NOT NULL DEFAULT 'munich',
                    fit_score INTEGER NOT NULL,
                    role_archetype TEXT,
                    seniority TEXT,
                    technical_alignment INTEGER,
                    seniority_impact INTEGER,
                    location_commute INTEGER,
                    company_mission INTEGER,
                    comp_potential INTEGER,
                    matching_pillars TEXT,
                    key_strengths TEXT,
                    gaps_risks TEXT,
                    pitch_strategy TEXT,
                    opportunity_file TEXT,
                    tailored_letter_file TEXT,
                    compensation_estimate TEXT,
                    evaluated_at TEXT NOT NULL,
                    PRIMARY KEY (posting_id, region)
                );
            """)
            conn.execute("""
                INSERT OR IGNORE INTO evaluations_new (
                    posting_id, region, fit_score, role_archetype, seniority,
                    technical_alignment, seniority_impact, location_commute,
                    company_mission, comp_potential, matching_pillars,
                    key_strengths, gaps_risks, pitch_strategy,
                    opportunity_file, tailored_letter_file, evaluated_at
                )
                SELECT
                    posting_id, 'munich', fit_score, role_archetype, seniority,
                    technical_alignment, seniority_impact, location_commute,
                    company_mission, comp_potential, matching_pillars,
                    key_strengths, gaps_risks, pitch_strategy,
                    opportunity_file, tailored_letter_file, evaluated_at
                FROM evaluations;
            """)
            conn.execute("DROP TABLE evaluations;")
            conn.execute("ALTER TABLE evaluations_new RENAME TO evaluations;")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evaluations (
                    posting_id TEXT REFERENCES postings(id) ON DELETE CASCADE,
                    region TEXT NOT NULL DEFAULT 'munich',
                    fit_score INTEGER NOT NULL,
                    role_archetype TEXT,
                    seniority TEXT,
                    technical_alignment INTEGER,
                    seniority_impact INTEGER,
                    location_commute INTEGER,
                    company_mission INTEGER,
                    comp_potential INTEGER,
                    matching_pillars TEXT,
                    key_strengths TEXT,
                    gaps_risks TEXT,
                    pitch_strategy TEXT,
                    opportunity_file TEXT,
                    tailored_letter_file TEXT,
                    compensation_estimate TEXT,
                    evaluated_at TEXT NOT NULL,
                    PRIMARY KEY (posting_id, region)
                );
            """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_postings_status ON postings(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_score_reg ON evaluations(region, fit_score);")

def hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

def is_seen(db_path: Path, canonical_url: str, content_hash: Optional[str] = None) -> bool:
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        if content_hash:
            cur.execute("SELECT id FROM postings WHERE canonical_url = ? OR content_hash = ?", (canonical_url, content_hash))
        else:
            cur.execute("SELECT id FROM postings WHERE canonical_url = ?", (canonical_url,))
        return cur.fetchone() is not None

def upsert_posting(db_path: Path, posting: Dict[str, Any]) -> str:
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        post_id = posting.get("id") or hashlib.md5(posting["canonical_url"].encode("utf-8")).hexdigest()[:16]
        c_hash = posting.get("content_hash") or hash_content(posting.get("raw_content", ""))
        now_str = datetime.utcnow().isoformat() + "Z"

        cur.execute("""
            INSERT INTO postings (
                id, canonical_url, company, title, location, workplace_type, 
                department, ats_source, raw_content, content_hash, discovered_at, posted_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_url) DO UPDATE SET
                title = excluded.title,
                location = excluded.location,
                raw_content = excluded.raw_content,
                content_hash = excluded.content_hash
        """, (
            post_id,
            posting["canonical_url"],
            posting["company"],
            posting["title"],
            posting.get("location", ""),
            posting.get("workplace_type", ""),
            posting.get("department", ""),
            posting.get("ats_source", ""),
            posting.get("raw_content", ""),
            c_hash,
            posting.get("discovered_at", now_str),
            posting.get("posted_at"),
            posting.get("status", "new")
        ))
        return post_id

def save_evaluation(db_path: Path, evaluation: Dict[str, Any], region: str = "munich"):
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        pillars_str = ",".join(evaluation.get("matching_pillars", [])) if isinstance(evaluation.get("matching_pillars"), list) else evaluation.get("matching_pillars", "")
        strengths_str = " | ".join(evaluation.get("key_strengths", [])) if isinstance(evaluation.get("key_strengths"), list) else evaluation.get("key_strengths", "")
        gaps_str = " | ".join(evaluation.get("gaps_risks", [])) if isinstance(evaluation.get("gaps_risks"), list) else evaluation.get("gaps_risks", "")
        now_str = datetime.utcnow().isoformat() + "Z"

        comp_data = evaluation.get("compensation") or evaluation.get("compensation_estimate")
        comp_json = json.dumps(comp_data) if comp_data else None
        reg = evaluation.get("region") or region

        cur.execute("""
            INSERT INTO evaluations (
                posting_id, region, fit_score, role_archetype, seniority, technical_alignment,
                seniority_impact, location_commute, company_mission, comp_potential,
                matching_pillars, key_strengths, gaps_risks, pitch_strategy,
                opportunity_file, tailored_letter_file, compensation_estimate, evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(posting_id, region) DO UPDATE SET
                fit_score = excluded.fit_score,
                role_archetype = excluded.role_archetype,
                seniority = excluded.seniority,
                technical_alignment = excluded.technical_alignment,
                seniority_impact = excluded.seniority_impact,
                location_commute = excluded.location_commute,
                company_mission = excluded.company_mission,
                comp_potential = excluded.comp_potential,
                matching_pillars = excluded.matching_pillars,
                key_strengths = excluded.key_strengths,
                gaps_risks = excluded.gaps_risks,
                pitch_strategy = excluded.pitch_strategy,
                opportunity_file = COALESCE(excluded.opportunity_file, evaluations.opportunity_file),
                tailored_letter_file = COALESCE(excluded.tailored_letter_file, evaluations.tailored_letter_file),
                compensation_estimate = COALESCE(excluded.compensation_estimate, evaluations.compensation_estimate),
                evaluated_at = excluded.evaluated_at
        """, (
            evaluation["posting_id"],
            reg,
            evaluation["fit_score"],
            evaluation.get("role_archetype", ""),
            evaluation.get("seniority", ""),
            evaluation.get("technical_alignment", 0),
            evaluation.get("seniority_impact", 0),
            evaluation.get("location_commute", 0),
            evaluation.get("company_mission", 0),
            evaluation.get("comp_potential", 0),
            pillars_str,
            strengths_str,
            gaps_str,
            evaluation.get("pitch_strategy", ""),
            evaluation.get("opportunity_file"),
            evaluation.get("tailored_letter_file"),
            comp_json,
            now_str
        ))
        cur.execute("UPDATE postings SET status = 'scored' WHERE id = ? AND status = 'new'", (evaluation["posting_id"],))

def get_unscored_postings(db_path: Path, region: str = "munich") -> List[Dict[str, Any]]:
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.* FROM postings p
            LEFT JOIN evaluations e ON p.id = e.posting_id AND e.region = ?
            WHERE e.posting_id IS NULL OR p.status = 'new'
        """, (region,))
        return [dict(row) for row in cur.fetchall()]

def get_stats(db_path: Path) -> Dict[str, Any]:
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM postings")
        total = cur.fetchone()[0]

        cur.execute("SELECT DISTINCT region FROM evaluations")
        regions = [r[0] for r in cur.fetchall()] or ["munich"]

        regional_stats = {}
        for reg in regions:
            cur.execute("SELECT COUNT(*) FROM evaluations WHERE region = ? AND fit_score >= 85", (reg,))
            high = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM evaluations WHERE region = ? AND fit_score >= 70 AND fit_score < 85", (reg,))
            pot = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM evaluations WHERE region = ? AND fit_score < 70", (reg,))
            low = cur.fetchone()[0]
            regional_stats[reg] = {
                "high_fit": high,
                "potential_fit": pot,
                "low_fit": low
            }

        return {
            "total_postings": total,
            "regions": regional_stats
        }

def compute_job_id(company: str = "", title: str = "", external_id: Optional[str] = None, url: Optional[str] = None, **kwargs) -> str:
    raw = f"{company.strip().lower()}:{title.strip().lower()}"
    if external_id:
        raw += f":{external_id}"
    elif url:
        raw += f":{url}"
    elif not raw or raw == ":":
        raw = kwargs.get("canonical_url", "")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]
