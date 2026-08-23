"""Arabic text normalization and cleaning utilities.

Two text copies are kept throughout the pipeline:
- original text: for display and publishing (never normalized)
- matching text: normalized copy used only for dedup/clustering/claim checks
"""
import re
import unicodedata

TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
TATWEEL = "ـ"
ZERO_WIDTH = re.compile(r"[​‌‍⁠﻿]")
BIDI_CONTROLS = re.compile(r"[‪-‮⁦-⁩‎‏]")
ARABIC_CHAR = re.compile(r"[؀-ۿ]")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|مليون|مليار|ريال|دولار|جنيه)?")
QUOTED_RE = re.compile(r'[«“"]([^»”"]{3,120})[»”"]')

ALEF_FORMS = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"}


def clean_text(text: str) -> str:
    """Unicode-safe cleaning for display text: NFC, strip zero-width and bidi controls."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = ZERO_WIDTH.sub("", text)
    text = BIDI_CONTROLS.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_for_matching(text: str, unify_taa: bool = False) -> str:
    """Aggressive normalization used ONLY for similarity/matching, never for display."""
    text = clean_text(text)
    text = URL_RE.sub(" ", text)
    text = TASHKEEL.sub("", text)
    text = text.replace(TATWEEL, "")
    for src, dst in ALEF_FORMS.items():
        text = text.replace(src, dst)
    text = text.replace("ى", "ي")  # alef maqsoora -> yaa
    if unify_taa:
        text = text.replace("ة", "ه")  # taa marbuta -> haa
    text = re.sub(r"[^\w\s؀-ۿ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def arabic_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    ar = sum(1 for c in letters if ARABIC_CHAR.match(c))
    return ar / len(letters)


def is_mostly_arabic(text: str, threshold: float = 0.6) -> bool:
    return arabic_ratio(text) >= threshold


def extract_claims(text: str) -> dict:
    """Deterministic claim extraction: numbers, quoted statements. Used for hallucination checks."""
    normalized = normalize_for_matching(text)
    numbers = set(NUMBER_RE.findall(text))
    quoted = {normalize_for_matching(q) for q in QUOTED_RE.findall(text)}
    tokens = set(normalized.split())
    return {"numbers": numbers, "quoted": quoted, "tokens": tokens}
