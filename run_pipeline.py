#!/usr/bin/env python3
"""نقطة تشغيل الخط من سطر الأوامر — يستخدمها cron و GitHub Actions.

python run_pipeline.py [--mock] [--query QUERY] [--timeframe 24h|7d|30d|all]

--mock: تشغيل كامل مع mock LLM providers ومجلّد fetcher stubbed (لا مفاتيح API، لا شبكة).
"""
from __future__ import annotations
import argparse
import os
import sys
import tempfile
import uuid


def _stub_fetch_all(sources, query="", **kwargs):
    """Stub fetcher for mock mode: returns 2 fake articles."""
    return [
        {"id": uuid.uuid4().hex[:12], "source_id": sources[0]["id"] if sources else None, "source_name": "Mock Source", "source_type": "rss", "title": "خبر تجريبي للوضع الوهمي", "link": "https://example.com/mock/1", "snippet": "هذا نص تجريبي لخبر وهمي يُستخدم لاختبار خط المعالجة بدون مفاتيح API أو شبكة.", "published": "", "published_dt": None, "direction": "rtl", "score": 1.0},
        {"id": uuid.uuid4().hex[:12], "source_id": sources[0]["id"] if sources else None, "source_name": "Mock Source", "source_type": "rss", "title": "خبر آخر للوضع الوهمي", "link": "https://example.com/mock/2", "snippet": "نص آخر لتجربة التجميع وإزالة التكرار في الوضع الوهمي.", "published": "", "published_dt": None, "direction": "rtl", "score": 0.9},
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the midya pipeline from CLI.")
    parser.add_argument("--mock", action="store_true", help="Run with mock LLM providers and stubbed fetcher (no API keys, no network).")
    parser.add_argument("--query", type=str, default="", help="Search query for fetching articles.")
    parser.add_argument("--timeframe", type=str, default="24h", choices=["24h", "7d", "30d", "all"], help="Timeframe for fetching articles.")
    args = parser.parse_args()

    if args.mock:
        os.environ["GENERATOR_PROVIDER"] = "mock"
        os.environ["JUDGE_PROVIDER"] = "mock"
        db_path = os.path.join(tempfile.gettempdir(), "midya_mock_test.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        import app.fetcher as fetcher_mod
        original_fetch_all = fetcher_mod.fetch_all
        fetcher_mod.fetch_all = _stub_fetch_all
        try:
            from app.pipeline import fetch_and_run
            stats = fetch_and_run(query=args.query, timeframe=args.timeframe, db_url=f"sqlite:///{db_path}")
        finally:
            fetcher_mod.fetch_all = original_fetch_all
        print(f"Mock run completed: {stats['generated']} generations, cost=${stats['cost_usd']:.6f}")
        return 0

    from app.pipeline import fetch_and_run
    stats = fetch_and_run(query=args.query, timeframe=args.timeframe)
    print(f"Pipeline completed: {stats['generated']} generations, cost=${stats['cost_usd']:.6f}, elapsed={stats['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())