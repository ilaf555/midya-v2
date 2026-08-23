"""جلب النص الكامل للمقالات من روابط RSS باستخدام trafilatura.

التثبيت:
    pip install trafilatura

الاستخدام داخل fetcher.py بعد تجميع عناصر RSS:
    from app.fulltext import enrich_items
    items = enrich_items(items)   # يضيف مفتاح full_text لكل عنصر
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import trafilatura

log = logging.getLogger(__name__)

# حد أقصى لطول النص — يحمي تكلفة توكنات LLM في خطوات التلخيص/التقييم
MAX_CHARS = 8000


def fetch_full_text(url: str, max_chars: int = MAX_CHARS) -> str | None:
    """يجلب النص الكامل لمقال واحد. يعيد None عند الفشل (حظر/ paywall / خطأ شبكة)."""
    try:
        html = trafilatura.fetch_url(url)
        if not html:
            return None
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_recall=True,   # استرجاع أوسع — مناسب للمواقع العربية
        )
        if not text:
            return None
        return text[:max_chars]
    except Exception as exc:  # noqa: BLE001
        log.warning("full-text fetch failed for %s: %s", url, exc)
        return None


def enrich_items(
    items: list[dict],
    url_key: str = "link",
    text_key: str = "full_text",
    max_workers: int = 5,
    delay: float = 0.4,
) -> list[dict]:
    """يُثري عناصر RSS بالنص الكامل بشكل متوازٍ مع حد لعدد العمال.

    - يتخطى العناصر التي لديها full_text مسبقًا (كاش طبيعي).
    - delay: مهلة لطف بين الطلبات حتى لا تُحظر من مواقع المصادر.
    """
    pending = [it for it in items if not it.get(text_key) and it.get(url_key)]
    log.info("fetching full text for %d/%d items", len(pending), len(items))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_full_text, it[url_key]): it for it in pending}
        for fut in as_completed(futures):
            item = futures[fut]
            text = fut.result()
            if text:
                item[text_key] = text
            time.sleep(delay)

    return items
