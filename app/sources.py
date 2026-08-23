"""Source management, ported from the Flask app (app-1.py) mechanism and
adapted to sqlite storage instead of sources.json.

Source schema (same as the Flask app):
{id, name, type: rss|site, url, category, language}
plus editorial fields: credibility (0..1), active.
"""
from __future__ import annotations
import time
import uuid

from . import db

VALID_TYPES = ("rss", "site")
VALID_LANGUAGES = ("ar", "en")

DEFAULT_SOURCES = [
    {"id": "src_1", "name": "BBC News", "type": "rss",
     "url": "http://feeds.bbci.co.uk/news/rss.xml", "category": "World", "language": "en"},
    {"id": "src_2", "name": "BBC Arabic", "type": "rss",
     "url": "https://feeds.bbci.co.uk/arabic/rss.xml", "category": "Arabic News", "language": "ar"},
    {"id": "src_3", "name": "Al Jazeera Arabic", "type": "rss",
     "url": "https://www.aljazeera.net/rss", "category": "Arabic News", "language": "ar"},
    {"id": "src_4", "name": "NY Times World", "type": "rss",
     "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "category": "World", "language": "en"},
    {"id": "src_5", "name": "Sky News Arabia", "type": "site",
     "url": "skynewsarabia.com", "category": "Arabic News", "language": "ar"},
    {"id": "src_6", "name": "TechCrunch", "type": "site",
     "url": "techcrunch.com", "category": "Technology", "language": "en"},
]


def validate_source(data: dict) -> list[str]:
    """Same rules as the Flask app's POST /api/sources."""
    errors = []
    name = (data.get("name") or "").strip()
    url = (data.get("url") or "").strip()
    stype = (data.get("type") or "rss").strip().lower()
    lang = (data.get("language") or "en").strip().lower()
    if not name or not url:
        errors.append("Source name and URL/domain are required.")
    if stype not in VALID_TYPES:
        errors.append('Source type must be "rss" or "site".')
    if stype == "rss" and not url.startswith(("http://", "https://")):
        errors.append("RSS sources need a full feed URL (http/https).")
    if lang not in VALID_LANGUAGES:
        errors.append('Language must be "ar" or "en".')
    return errors


def seed_defaults(conn) -> int:
    """Insert DEFAULT_SOURCES when the table is empty. Returns inserted count."""
    count = conn.execute("SELECT COUNT(*) AS c FROM sources").fetchone()["c"]
    if count:
        return 0
    for s in DEFAULT_SOURCES:
        _insert(conn, s, credibility=0.8)
    conn.commit()
    return len(DEFAULT_SOURCES)


def _insert(conn, s: dict, credibility: float = 0.5) -> dict:
    ext_id = s.get("id") or f"src_{uuid.uuid4().hex[:8]}"
    conn.execute(
        """INSERT OR IGNORE INTO sources(external_id, name, type, url, category,
           language, credibility, active, created_at) VALUES (?,?,?,?,?,?,?,1,?)""",
        (ext_id, s["name"].strip(), s["type"].strip().lower(), s["url"].strip(),
         (s.get("category") or "General").strip(), (s.get("language") or "en").strip().lower(),
         credibility, time.time()))
    return {**s, "id": ext_id}


def add_source(conn, data: dict) -> tuple[dict | None, list[str]]:
    """Validate then add. Returns (source, errors)."""
    errors = validate_source(data)
    if errors:
        return None, errors
    existing = conn.execute("SELECT 1 FROM sources WHERE url=? AND active=1",
                            ((data.get("url") or "").strip(),)).fetchone()
    if existing:
        return None, ["Source URL already exists."]
    source = _insert(conn, data, credibility=float(data.get("credibility", 0.5)))
    conn.commit()
    return source, []


def delete_source(conn, external_id: str) -> bool:
    """Soft delete (active=0) to keep article history auditable."""
    cur = conn.execute("UPDATE sources SET active=0 WHERE external_id=? AND active=1",
                       (external_id,))
    conn.commit()
    return cur.rowcount > 0


def list_sources(conn, active_only: bool = True) -> list[dict]:
    q = ("SELECT external_id AS id, name, type, url, category, language,"
         " credibility, active FROM sources")
    if active_only:
        q += " WHERE active=1"
    return [dict(r) for r in conn.execute(q + " ORDER BY name").fetchall()]


def set_credibility(conn, external_id: str, score: float) -> bool:
    cur = conn.execute("UPDATE sources SET credibility=? WHERE external_id=?",
                       (max(0.0, min(1.0, score)), external_id))
    conn.commit()
    return cur.rowcount > 0
