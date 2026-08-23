"""Main pipeline: fetch -> normalize -> dedup -> cluster -> generate ->
guardrails -> judge -> review/publish. Every stage is logged with cost."""
from __future__ import annotations
import json
import os
import re
import time
import uuid

from . import config, db
from .arabic import clean_text, normalize_for_matching
from .clustering import cluster_articles
from .dedup import DedupPipeline, Embedder, choose_parent
from .guardrails import run_cheap_checks
from .judge import judge_generation
from .llm import Usage, make_pair

GENERATOR_SYSTEM = (
    "أنت صحفي محرر. لخّص الخبر التالي بالعربية الفصحى الواضحة، والتزم تمامًا "
    "بمعلومات المصدر دون إضافة أي حقيقة غير واردة فيه. أجب بصيغة JSON بالمفاتيح: "
    "headline (عنوان قصير), summary (ملخص 3-5 جمل), post (منشور تواصل اجتماعي "
    "أقل من 280 حرفًا), category (تصنيف واحد)."
)

STYLE_PROFILES = {
    "formal": "استخدم أسلوبًا إخباريًا رسميًا محايدًا.",
    "social": "استخدم أسلوبًا خفيفًا مناسبًا لمنصات التواصل دون مبالغة.",
}


class Pipeline:
    def __init__(self, db_url: str | None = None, style: str = "formal"):
        if db_url:
            os.environ["DATABASE_URL"] = db_url
        self.conn = db.get_conn()
        self.usage = Usage()
        self.generator, self.judge = make_pair(self.usage)
        self.embedder = Embedder(config.EMBEDDING_MODEL)
        self.dedup = DedupPipeline(self.embedder)
        self.style_prompt = STYLE_PROFILES.get(style, STYLE_PROFILES["formal"])

    def prepare(self, raw_articles: list[dict]) -> list[dict]:
        """raw_articles: [{source, url, title, text, published_ts}]"""
        prepared = []
        for a in raw_articles:
            original = clean_text(a.get("text", ""))
            if len(original) < 80:
                continue
            prepared.append({
                "id": a.get("id") or uuid.uuid4().hex[:12],
                "source": a.get("source", "unknown"),
                "url": a.get("url", ""),
                "title": clean_text(a.get("title", ""))[:500],
                "original_text": original,
                "match_text": normalize_for_matching(original)[:8000],
                "published_ts": float(a.get("published_ts") or time.time()),
            })
        return prepared

    def fetch_and_run(self, query: str = "", timeframe: str = "24h",
                      deep_search: bool = False, category: str = "all",
                      from_date: str | None = None, to_date: str | None = None) -> dict:
        """Fetch from managed sources (app-1.py mechanism) then run the pipeline."""
        from . import fetcher, sources as sources_mod
        sources_mod.seed_defaults(self.conn)
        srcs = sources_mod.list_sources(self.conn)
        if category != "all":
            srcs = [s for s in srcs if (s.get("category") or "").lower() == category.lower()]
        items = fetcher.fetch_all(srcs, query=query, deep_search=deep_search,
                                  timeframe=timeframe, from_date=from_date, to_date=to_date)
        articles = fetcher.to_pipeline_articles(items)
        stats = self.run(articles)
        stats["fetched"] = len(items)
        stats["sources_used"] = len(srcs)
        return stats

    def run(self, raw_articles: list[dict]) -> dict:
        started = time.time()
        articles = self.prepare(raw_articles)
        dedup_result = self.dedup.run(articles)
        kept = dedup_result.kept

        dup_map: dict[str, list[tuple]] = {}
        for dup_id, pid, score, stage in dedup_result.duplicates:
            dup_map.setdefault(pid, []).append((dup_id, pid, score, stage))
        by_id_all = {a["id"]: a for a in articles}

        sim = (self.embedder.similarity_matrix([a["match_text"][:2000] for a in kept])
               if len(kept) > 1 else None)
        clusters = cluster_articles(kept, sim) if sim is not None else ([kept] if kept else [])

        credibility = db.get_credibility_map(self.conn)
        stats = {"ingested": len(raw_articles), "prepared": len(articles),
                 "duplicates": len(dedup_result.duplicates), "clusters": len(clusters),
                 "generated": 0, "auto_approved": 0, "needs_review": 0, "blocked": 0}

        for group in clusters:
            parent = choose_parent(group, credibility)
            cluster_id = db.insert_cluster(self.conn)
            row_ids = {}
            for a in group:
                dup = next((d for d in dedup_result.duplicates if d[0] == a["id"]), None)
                row_ids[a["id"]] = db.insert_article(self.conn, a, cluster_id, dup)
            for a in group:  # persist duplicates for audit trail
                for dup in dup_map.get(a["id"], []):
                    da = by_id_all.get(dup[0])
                    if da:
                        db.insert_article(self.conn, da, cluster_id, dup,
                                          duplicate_of=row_ids[a["id"]])

            siblings = [g for g in group if g["id"] != parent["id"]]
            context = parent["original_text"][:5000]
            if siblings:
                context += "\n\nتغطيات أخرى للحدث نفسه:\n" + "\n---\n".join(
                    s["original_text"][:1500] for s in siblings[:3])

            t0 = time.time()
            raw = self.generator.generate(
                GENERATOR_SYSTEM, self.style_prompt + "\n\n" + context,
                max_tokens=1200, temperature=0.3)
            latency = time.time() - t0

            try:
                m = re.search(r"\{.*\}", raw, re.S)
                payload = json.loads(m.group(0)) if m else {}
            except json.JSONDecodeError:
                payload = {}
            summary = str(payload.get("summary", "")).strip()
            post = str(payload.get("post", "")).strip()
            if not summary:
                stats["blocked"] += 1
                continue

            guard = run_cheap_checks(summary + "\n" + post, require_arabic=True)
            judge_res = judge_generation(self.judge, parent["original_text"], summary)
            status = "needs_review"
            if guard.passed and judge_res.auto_publishable and config.AUTO_PUBLISH:
                status = "auto_approved"
            stats["generated"] += 1
            stats[status] += 1

            db.insert_generation(self.conn, {
                "cluster_id": cluster_id,
                "headline": str(payload.get("headline", ""))[:500],
                "summary": summary, "post_text": post,
                "category": str(payload.get("category", ""))[:80],
                "prompt_version": config.PROMPT_VERSION,
                "generator_provider": self.generator.provider,
                "judge_provider": self.judge.provider,
                "judge_scores": judge_res.scores,
                "judge_verdict": judge_res.verdict,
                "unverified_claims": judge_res.unverified_claims,
                "guardrail_reasons": guard.reasons,
                "status": status,
                "cost_usd": round(self.usage.cost_usd, 6),
                "latency_s": round(latency, 3)})

        self.conn.commit()
        stats["cost_usd"] = round(self.usage.cost_usd, 6)
        stats["elapsed_s"] = round(time.time() - started, 2)
        stats["embedder_mode"] = self.embedder.mode
        return stats
