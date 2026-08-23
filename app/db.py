"""Storage layer on stdlib sqlite3 (zero external deps).

Set DATABASE_URL=sqlite:///midya.db (default). The schema is simple enough
to migrate to Postgres later if the project grows.
"""
from __future__ import annotations
import json
import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    external_id TEXT UNIQUE,
    name TEXT, type TEXT DEFAULT 'rss', url TEXT,
    category TEXT DEFAULT 'General', language TEXT DEFAULT 'en',
    credibility REAL DEFAULT 0.5, active INTEGER DEFAULT 1,
    created_at REAL);
CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY, created_at REAL);
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY, external_id TEXT, source TEXT, url TEXT,
    title TEXT, original_text TEXT, match_text TEXT, published_ts REAL,
    cluster_id INTEGER, is_duplicate INTEGER DEFAULT 0,
    duplicate_of INTEGER, dup_stage TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY, cluster_id INTEGER, headline TEXT, summary TEXT,
    post_text TEXT, category TEXT, prompt_version TEXT,
    generator_provider TEXT, judge_provider TEXT,
    judge_scores TEXT, judge_verdict TEXT, unverified_claims TEXT,
    guardrail_reasons TEXT, status TEXT DEFAULT 'needs_review',
    cost_usd REAL DEFAULT 0, latency_s REAL DEFAULT 0, created_at REAL);
CREATE INDEX IF NOT EXISTS idx_gen_status ON generations(status);
"""

# Columns added after v1: applied idempotently for existing databases.
MIGRATIONS = [
    "ALTER TABLE sources ADD COLUMN external_id TEXT",
    "ALTER TABLE sources ADD COLUMN type TEXT DEFAULT 'rss'",
    "ALTER TABLE sources ADD COLUMN category TEXT DEFAULT 'General'",
    "ALTER TABLE sources ADD COLUMN language TEXT DEFAULT 'en'",
    "ALTER TABLE sources ADD COLUMN created_at REAL",
]


def db_path() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///midya.db")
    return url.replace("sqlite:///", "") if url.startswith("sqlite:///") else url


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for stmt in MIGRATIONS:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column already exists
    return conn


def get_credibility_map(conn) -> dict:
    return {r["name"]: r["credibility"]
            for r in conn.execute("SELECT name, credibility FROM sources WHERE active=1")}


def insert_cluster(conn) -> int:
    cur = conn.execute("INSERT INTO clusters(created_at) VALUES (?)", (time.time(),))
    return cur.lastrowid


def insert_article(conn, a: dict, cluster_id: int | None, dup: tuple | None,
                   duplicate_of: int | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO articles(external_id, source, url, title, original_text,
           match_text, published_ts, cluster_id, is_duplicate, duplicate_of,
           dup_stage, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a["id"], a["source"], a["url"], a["title"], a["original_text"],
         a["match_text"], a["published_ts"], cluster_id,
         1 if dup else 0, duplicate_of, dup[3] if dup else "", time.time()))
    return cur.lastrowid


def insert_generation(conn, g: dict) -> int:
    cur = conn.execute(
        """INSERT INTO generations(cluster_id, headline, summary, post_text,
           category, prompt_version, generator_provider, judge_provider,
           judge_scores, judge_verdict, unverified_claims, guardrail_reasons,
           status, cost_usd, latency_s, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (g["cluster_id"], g["headline"], g["summary"], g["post_text"],
         g["category"], g["prompt_version"], g["generator_provider"],
         g["judge_provider"], json.dumps(g["judge_scores"], ensure_ascii=False),
         g["judge_verdict"], json.dumps(g["unverified_claims"], ensure_ascii=False),
         json.dumps(g["guardrail_reasons"], ensure_ascii=False), g["status"],
         g["cost_usd"], g["latency_s"], time.time()))
    conn.commit()
    return cur.lastrowid


def list_generations(conn, statuses=("needs_review", "auto_approved"), limit: int = 50):
    marks = ",".join("?" * len(statuses))
    rows = conn.execute(
        f"SELECT * FROM generations WHERE status IN ({marks}) "
        f"ORDER BY created_at DESC LIMIT ?", (*statuses, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["judge_scores"] = json.loads(d["judge_scores"] or "{}")
        d["unverified_claims"] = json.loads(d["unverified_claims"] or "[]")
        d["guardrail_reasons"] = json.loads(d["guardrail_reasons"] or "[]")
        out.append(d)
    return out


def update_generation(conn, gen_id: int, status: str, post_text: str | None = None):
    if post_text is not None:
        conn.execute("UPDATE generations SET status=?, post_text=? WHERE id=?",
                     (status, post_text, gen_id))
    else:
        conn.execute("UPDATE generations SET status=? WHERE id=?", (status, gen_id))
    conn.commit()


def all_generations(conn):
    rows = conn.execute("SELECT * FROM generations").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["judge_scores"] = json.loads(d["judge_scores"] or "{}")
        out.append(d)
    return out
