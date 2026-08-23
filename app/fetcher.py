"""Fetching layer ported from the Flask app (app-1.py):
live RSS reading + site: archive search with Arabic localization,
Google Web / DuckDuckGo fallbacks, parallel fetching, timeframe filters.

feedparser is used when installed; otherwise a builtin RSS/Atom parser
(stdlib xml.etree) keeps RSS sources working.
"""
from __future__ import annotations
import html
import re
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import requests

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}
TIMEOUT = 7

try:
    import feedparser
except ImportError:
    feedparser = None


# ---------- text helpers (from app-1.py) ----------

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", str(raw_html))
    clean = html.unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()


def detect_direction(text: str) -> str:
    if not text:
        return "ltr"
    if re.search(r"[؀-ۿݐ-ݿࢠ-ࣿ]", text):
        return "rtl"
    return "ltr"


def extract_base_domain(url_or_domain: str) -> str:
    if not url_or_domain:
        return ""
    s = url_or_domain.strip().lower()
    if not s.startswith(("http://", "https://")):
        s = "http://" + s
    try:
        netloc = urllib.parse.urlparse(s).netloc
        netloc = re.sub(r"^(www|feeds|rss|news|edition)\d*\.", "", netloc)
        if netloc in ("bbci.co.uk", "bbc.co.uk"):
            return "bbc.com"
        return netloc
    except Exception:
        return url_or_domain


def normalize_url(url: str) -> str:
    """Strip tracking params (utm_*, oc=) for deduplication."""
    if not url:
        return ""
    url = url.split("?oc=")[0].split("&oc=")[0]
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    filtered = {k: v for k, v in qs.items() if not k.startswith("utm_")}
    clean = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path,
                                     parsed.params, urllib.parse.urlencode(filtered, doseq=True), ""))
    return clean.rstrip("/")


def calculate_relevance_score(query: str, title: str, snippet: str) -> float:
    if not query:
        return 1.0
    tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 1]
    if not tokens:
        return 1.0
    title_l, snippet_l = title.lower(), snippet.lower()
    score = 0.0
    full = query.lower().strip()
    if full in title_l:
        score += 10.0
    if full in snippet_l:
        score += 4.0
    for token in tokens:
        if token in title_l:
            score += 3.0
        if token in snippet_l:
            score += 1.0
    return score


# ---------- time filtering (from app-1.py) ----------

def is_within_timeframe(dt: datetime | None, timeframe: str,
                        from_date: str | None = None, to_date: str | None = None) -> bool:
    if not dt or timeframe == "all":
        return True
    now = datetime.now()
    if timeframe == "24h":
        return dt >= now - timedelta(hours=24)
    if timeframe == "7d":
        return dt >= now - timedelta(days=7)
    if timeframe == "30d":
        return dt >= now - timedelta(days=30)
    if timeframe == "1y":
        return dt >= now - timedelta(days=365)
    if timeframe == "custom":
        try:
            if from_date and dt < datetime.strptime(from_date, "%Y-%m-%d"):
                return False
            if to_date and dt > datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1):
                return False
        except ValueError:
            return True
    return True


def build_timeframe_search_operator(timeframe: str, from_date=None, to_date=None) -> tuple[str, str]:
    ops = {"24h": ("when:24h", "qdr:d"), "7d": ("when:7d", "qdr:w"),
           "30d": ("when:30d", "qdr:m"), "1y": ("when:1y", "qdr:y")}
    if timeframe in ops:
        return ops[timeframe]
    if timeframe == "custom" and from_date and to_date:
        return (f"after:{from_date} before:{to_date}",
                f"cdr:1,cd_min:{from_date},cd_max:{to_date}")
    return "", ""


# ---------- feed parsing: feedparser or builtin fallback ----------

def _parse_dt_any(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).replace(tzinfo=None)
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def parse_feed(content: bytes) -> list[dict]:
    """Returns [{title, summary, link, published, published_ts}]."""
    if feedparser is not None:
        feed = feedparser.parse(content)
        out = []
        for e in feed.entries:
            parsed = e.get("published_parsed") or e.get("updated_parsed")
            dt = datetime(*parsed[:6]) if parsed else None
            out.append({
                "title": clean_html(e.get("title", "")),
                "summary": clean_html(e.get("summary", e.get("description", ""))),
                "link": e.get("link", ""),
                "published": e.get("published", e.get("updated", "")),
                "published_dt": dt,
            })
        return out
    import xml.etree.ElementTree as ET
    root = ET.fromstring(content)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    out = []
    for it in items:
        def txt(*names):
            for n in names:
                el = it.find(n)
                if el is not None and el.text:
                    return el.text
            return ""
        link = txt("link")
        if not link:  # Atom <link href="..."/>
            el = it.find("{http://www.w3.org/2005/Atom}link")
            link = el.get("href", "") if el is not None else ""
        published = txt("pubDate", "published", "updated",
                        "{http://www.w3.org/2005/Atom}published",
                        "{http://www.w3.org/2005/Atom}updated")
        out.append({
            "title": clean_html(txt("title", "{http://www.w3.org/2005/Atom}title")),
            "summary": clean_html(txt("description", "summary",
                                      "{http://www.w3.org/2005/Atom}summary",
                                      "{http://www.w3.org/2005/Atom}content")),
            "link": link.strip(),
            "published": published,
            "published_dt": _parse_dt_any(published),
        })
    return out


# ---------- fetchers (from app-1.py) ----------

def _mk_item(source, stype, title, link, snippet, published, dt, query):
    return {
        "id": uuid.uuid4().hex[:12],
        "source_id": source.get("id"),
        "source_name": source.get("name"),
        "source_type": stype,
        "title": title,
        "link": link,
        "snippet": snippet,
        "published": published or "",
        "published_dt": dt,
        "direction": detect_direction(title + " " + snippet),
        "score": calculate_relevance_score(query, title, snippet),
    }


def fetch_rss_live(source: dict, query: str, timeframe: str = "all",
                   from_date=None, to_date=None) -> list[dict]:
    results = []
    try:
        resp = requests.get(source["url"], headers=HTTP_HEADERS, timeout=TIMEOUT)
        if resp.status_code != 200:
            return results
        tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 1] if query else []
        for e in parse_feed(resp.content):
            dt = e["published_dt"]
            if dt and not is_within_timeframe(dt, timeframe, from_date, to_date):
                continue
            combined = f"{e['title']} {e['summary']}".lower()
            if tokens and not any(t in combined for t in tokens):
                continue
            results.append(_mk_item(source, "rss", e["title"], e["link"],
                                    e["summary"], e["published"], dt, query))
    except Exception:
        pass
    return results


def fetch_site_operator_search(source: dict, query: str, deep_search: bool = True,
                               timeframe: str = "all", from_date=None, to_date=None) -> list[dict]:
    results = []
    if not query:
        query = "news"
    domain = extract_base_domain(source.get("url", "")) or source.get("url", "").strip()
    tf_op, tbs_param = build_timeframe_search_operator(timeframe, from_date, to_date)
    search_query = f"site:{domain} {query} {tf_op}".strip()
    encoded = urllib.parse.quote(search_query)

    lang = (source.get("language") or "en").lower()
    if lang == "ar" or detect_direction(query) == "rtl":
        news_url = f"https://news.google.com/rss/search?q={encoded}&hl=ar&gl=AE&ceid=AE:ar"
    else:
        news_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = requests.get(news_url, headers=HTTP_HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            limit = 50 if deep_search else 20
            for e in parse_feed(resp.content)[:limit]:
                dt = e["published_dt"]
                if dt and not is_within_timeframe(dt, timeframe, from_date, to_date):
                    continue
                results.append(_mk_item(source, "google", e["title"], e["link"],
                                        e["summary"], e["published"], dt, query))
    except Exception:
        pass

    if len(results) < 5:  # DuckDuckGo fallback
        try:
            resp = requests.post("https://html.duckduckgo.com/html/?q=" + encoded,
                                 headers=HTTP_HEADERS, data={"q": search_query}, timeout=6)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                for div in soup.select("div.result"):
                    t_a = div.select_one("a.result__a")
                    s_a = div.select_one("a.result__snippet")
                    if not t_a:
                        continue
                    href = t_a.get("href", "")
                    if "uddg=" in href:
                        m = re.search(r"uddg=([^&]+)", href)
                        if m:
                            href = urllib.parse.unquote(m.group(1))
                    title = clean_html(t_a.get_text())
                    snippet = clean_html(s_a.get_text()) if s_a else ""
                    if href.startswith("http") and title:
                        results.append(_mk_item(source, "google", title, href,
                                                snippet, "", None, query))
        except Exception:
            pass
    return results


def fetch_unified_source(source: dict, query: str, deep_search: bool = True,
                         timeframe: str = "all", from_date=None, to_date=None) -> list[dict]:
    """RSS sources: live feed + archive search. Site sources: archive search only."""
    if source.get("type") == "rss":
        items = fetch_rss_live(source, query, timeframe, from_date, to_date)
        if query or deep_search:
            items.extend(fetch_site_operator_search(source, query, deep_search,
                                                    timeframe, from_date, to_date))
        return items
    return fetch_site_operator_search(source, query, deep_search, timeframe, from_date, to_date)


def deduplicate_results(results: list[dict]) -> list[dict]:
    """Cheap pre-dedup (normalized URL + title). The pipeline's semantic dedup runs after."""
    seen_urls, seen_titles, unique = set(), set(), []
    for item in results:
        norm_url = normalize_url(item.get("link", ""))
        norm_title = re.sub(r"\W+", "", item.get("title", "").lower())
        if norm_url and norm_url in seen_urls:
            continue
        if norm_title and norm_title in seen_titles and len(norm_title) > 8:
            continue
        if norm_url:
            seen_urls.add(norm_url)
        if norm_title:
            seen_titles.add(norm_title)
        unique.append(item)
    return unique


def fetch_all(sources: list[dict], query: str = "", deep_search: bool = False,
              timeframe: str = "24h", from_date=None, to_date=None,
              sort_by: str = "relevance") -> list[dict]:
    raw: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(15, max(1, len(sources)))) as ex:
        futures = {ex.submit(fetch_unified_source, s, query, deep_search,
                             timeframe, from_date, to_date): s for s in sources}
        for fut in as_completed(futures):
            try:
                raw.extend(fut.result())
            except Exception:
                pass
    results = deduplicate_results(raw)
    if sort_by == "relevance":
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results


def to_pipeline_articles(items: list[dict]) -> list[dict]:
    """Convert fetch items to the Pipeline input format.
    Note: search items carry summaries/snippets, not full article text."""
    out = []
    for it in items:
        text = (it.get("snippet") or "").strip()
        if it.get("title"):
            text = it["title"] + "\n" + text
        ts = time.time()
        if it.get("published_dt"):
            ts = it["published_dt"].timestamp()
        out.append({"id": it["id"], "source": it.get("source_name") or "unknown",
                    "url": it.get("link", ""), "title": it.get("title", ""),
                    "text": text, "published_ts": ts})
    return out
