"""Cross-model quality judge + deterministic claim verification.

The judge model must differ from the generator model. Scores are 1-5 per axis.
Claim verification is retrieval-based: every number/quote in the generated
text must appear in the source text (after Arabic normalization).
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field

from .arabic import extract_claims, normalize_for_matching

AUTO_PUBLISH_MIN_SCORE = 4.0

JUDGE_SYSTEM = (
    "أنت محرّر صحفي محترف تقيّم ملخصًا عربيًا مولّدًا آليًا مقابل نص المصدر. "
    "أجب بصيغة JSON فقط بالمفاتيح: accuracy, fidelity, tone, language "
    "(أعداد صحيحة 1-5), verdict (pass/fail), issues (قائمة نصية قصيرة). "
    "accuracy: هل الحقائق صحيحة؟ fidelity: هل يلتزم بالمصدر دون إضافات؟ "
    "tone: ملاءمة النبرة. language: سلامة اللغة العربية."
)


@dataclass
class JudgeResult:
    scores: dict = field(default_factory=dict)
    verdict: str = "fail"
    issues: list[str] = field(default_factory=list)
    unverified_claims: list[str] = field(default_factory=list)

    @property
    def avg_score(self) -> float:
        vals = [v for v in self.scores.values() if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def auto_publishable(self) -> bool:
        return (self.verdict == "pass"
                and self.avg_score >= AUTO_PUBLISH_MIN_SCORE
                and not self.unverified_claims)


def verify_claims(source_text: str, generated_text: str) -> list[str]:
    """Returns list of claims present in generated text but absent from source."""
    gen = extract_claims(generated_text)
    src_norm = normalize_for_matching(source_text)
    problems = []
    for num in gen["numbers"]:
        if num and num not in source_text and normalize_for_matching(num) not in src_norm:
            problems.append(f"number-not-in-source: {num}")
    for q in gen["quoted"]:
        if q and q not in src_norm:
            problems.append(f"quote-not-in-source: {q[:60]}")
    return problems


def judge_generation(judge_client, source_text: str, generated_text: str) -> JudgeResult:
    prompt = (
        "نص المصدر:\n" + source_text[:6000]
        + "\n\nالنص المولّد:\n" + generated_text[:3000]
        + "\n\nقيّم النص المولّد مقابل المصدر."
    )
    raw = judge_client.generate(JUDGE_SYSTEM, prompt, max_tokens=600, temperature=0.0)
    result = JudgeResult()
    try:
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0)) if m else {}
        result.scores = {k: data.get(k) for k in ("accuracy", "fidelity", "tone", "language")}
        result.verdict = str(data.get("verdict", "fail")).lower()
        result.issues = list(data.get("issues", []))[:10]
    except (json.JSONDecodeError, AttributeError):
        result.issues = ["judge-parse-error"]
    result.unverified_claims = verify_claims(source_text, generated_text)
    return result
