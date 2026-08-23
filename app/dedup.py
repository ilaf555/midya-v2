"""Three-stage deduplication pipeline.

Stage 1: exact URL/content hash (O(n), free)
Stage 2: MinHash LSH candidate selection + Jaccard confirm (cheap)
Stage 3: embedding cosine similarity (semantic) + Levenshtein confirm

Reference thresholds (news industry pipelines):
- cosine >= 0.95 -> near-identical articles
- Levenshtein ratio >= 0.97 titles / >= 0.92 content -> duplicate
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field

COSINE_DUP_THRESHOLD = 0.95
TITLE_LEV_THRESHOLD = 0.97
CONTENT_LEV_THRESHOLD = 0.92
JACCARD_CONFIRM = 0.55
NUM_PERM = 64
LSH_BANDS = 16


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def shingles(text: str, k: int = 4) -> set:
    tokens = text.split()
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class MinHashLSH:
    """Pure-python MinHash + banding LSH (no external deps)."""

    def __init__(self, num_perm: int = NUM_PERM, bands: int = LSH_BANDS):
        self.num_perm = num_perm
        self.bands = bands
        self.rows = num_perm // bands
        self.tables: list[dict] = [dict() for _ in range(bands)]
        self.sigs: dict[str, list[int]] = {}

    def _signature(self, sh: set) -> list[int]:
        sig = []
        for i in range(self.num_perm):
            best = None
            for token in sh:
                h = hash((i, token)) & 0xFFFFFFFFFFFF
                if best is None or h < best:
                    best = h
            sig.append(best if best is not None else 0)
        return sig

    def add(self, doc_id: str, sh: set) -> None:
        sig = self._signature(sh)
        self.sigs[doc_id] = sig
        for b in range(self.bands):
            band = tuple(sig[b * self.rows:(b + 1) * self.rows])
            self.tables[b].setdefault(band, set()).add(doc_id)

    def candidates(self, doc_id: str) -> set:
        sig = self.sigs[doc_id]
        out = set()
        for b in range(self.bands):
            band = tuple(sig[b * self.rows:(b + 1) * self.rows])
            out |= (self.tables[b].get(band, set()) - {doc_id})
        return out


def levenshtein_ratio(a: str, b: str) -> float:
    try:
        from rapidfuzz.fuzz import ratio
        return ratio(a, b) / 100.0
    except ImportError:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio()


class Embedder:
    """Multilingual embeddings with graceful fallbacks.

    Priority: sentence-transformers (e.g. paraphrase-multilingual-MiniLM / Qwen3-Embedding)
    -> sklearn TF-IDF cosine -> token Jaccard.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.mode = "jaccard"
        self._model = None
        self._tfidf = None
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
            self.mode = "sbert"
        except Exception:
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.metrics.pairwise import cosine_similarity  # noqa: F401
                self._tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
                self.mode = "tfidf"
            except Exception:
                self.mode = "jaccard"

    def similarity_matrix(self, texts: list[str]):
        import numpy as np
        if self.mode == "sbert":
            emb = self._model.encode(texts, normalize_embeddings=True)
            return np.asarray(emb) @ np.asarray(emb).T
        if self.mode == "tfidf":
            from sklearn.metrics.pairwise import cosine_similarity
            m = self._tfidf.fit_transform(texts)
            return cosine_similarity(m)
        n = len(texts)
        sim = np.eye(n)
        toks = [set(t.split()) for t in texts]
        for i in range(n):
            for j in range(i + 1, n):
                s = jaccard(toks[i], toks[j])
                sim[i, j] = sim[j, i] = s
        return sim


@dataclass
class DedupResult:
    kept: list[dict] = field(default_factory=list)
    duplicates: list[tuple[str, str, float, str]] = field(default_factory=list)  # (dup_id, parent_id, score, stage)


class DedupPipeline:
    def __init__(self, embedder: Embedder | None = None):
        self.embedder = embedder or Embedder()
        self.lsh = MinHashLSH()
        self.seen_hashes: set[str] = set()

    def run(self, articles: list[dict]) -> DedupResult:
        """articles: [{id, url, title, match_text, ...}] -> keeps parents, links duplicates."""
        result = DedupResult()
        unique = []
        for a in articles:  # stage 1
            h = content_hash(a["url"] or a["match_text"][:4000])
            if h in self.seen_hashes:
                result.duplicates.append((a["id"], "seen-hash", 1.0, "hash"))
                continue
            self.seen_hashes.add(h)
            unique.append(a)

        shingle_map = {a["id"]: shingles(a["match_text"]) for a in unique}
        for a in unique:  # stage 2 candidates
            self.lsh.add(a["id"], shingle_map[a["id"]])

        parent_of: dict[str, tuple[str, float, str]] = {}
        by_id = {a["id"]: a for a in unique}
        for a in unique:
            if a["id"] in parent_of:
                continue
            for cand in self.lsh.candidates(a["id"]):
                if cand in parent_of or cand == a["id"]:
                    continue
                b = by_id[cand]
                if jaccard(shingle_map[a["id"]], shingle_map[cand]) >= JACCARD_CONFIRM:
                    t = levenshtein_ratio(a["title"], b["title"])
                    c = levenshtein_ratio(a["match_text"][:3000], b["match_text"][:3000])
                    if t >= TITLE_LEV_THRESHOLD or c >= CONTENT_LEV_THRESHOLD:
                        parent_of[cand] = (a["id"], max(t, c), "minhash+lev")

        remaining = [a for a in unique if a["id"] not in parent_of]
        if len(remaining) > 1:  # stage 3 semantic
            sim = self.embedder.similarity_matrix([a["match_text"][:2000] for a in remaining])
            for i in range(len(remaining)):
                if remaining[i]["id"] in parent_of:
                    continue
                for j in range(i + 1, len(remaining)):
                    if remaining[j]["id"] in parent_of:
                        continue
                    if sim[i, j] >= COSINE_DUP_THRESHOLD:
                        parent_of[remaining[j]["id"]] = (remaining[i]["id"], float(sim[i, j]), "embedding")

        for dup_id, (pid, score, stage) in parent_of.items():
            result.duplicates.append((dup_id, pid, score, stage))
        result.kept = [a for a in unique if a["id"] not in parent_of]
        return result


def choose_parent(articles: list[dict], credibility: dict[str, float] | None = None) -> dict:
    """Pick the parent article of a cluster: source credibility, then recency, then length."""
    credibility = credibility or {}
    def score(a):
        return (
            credibility.get(a.get("source", ""), 0.5),
            a.get("published_ts", 0),
            len(a.get("original_text", "")),
        )
    return max(articles, key=score)
