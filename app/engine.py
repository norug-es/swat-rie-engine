import math
import re
import unicodedata
from dataclasses import dataclass

TOKEN_RE = re.compile(r"\b[\wáéíóúüñç]{3,}\b", re.IGNORECASE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

NEGATIONS = {
    "no", "not", "never", "nunca", "falso", "false", "denied", "niega",
    "incorrecto", "incorrect", "hoax", "fake"
}

STOP = {
    "the","and","for","with","that","this","from","have","has","was","were","are","but",
    "que","con","para","por","una","uno","del","las","los","como","más","este","esta",
    "sobre","entre","desde","han","hay","fue","son","sus","sin"
}

def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))

def tokens(s: str) -> set[str]:
    return {normalize(x) for x in TOKEN_RE.findall(s) if normalize(x) not in STOP}

def extract_claims(text: str, limit: int = 8) -> list[str]:
    candidates = []
    for sent in SENTENCE_RE.split(text.replace("\n", " ")):
        sent = re.sub(r"\s+", " ", sent).strip(" -•\t")
        if 25 <= len(sent) <= 400 and len(tokens(sent)) >= 4:
            candidates.append(sent)
    if not candidates and text.strip():
        candidates = [text.strip()[:400]]
    return candidates[:limit]

def _similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))

def _negation_flip(claim: str, evidence: str) -> float:
    c = tokens(claim)
    e = tokens(evidence)
    cneg = bool(c & NEGATIONS)
    eneg = bool(e & NEGATIONS)
    return 1.0 if cneg != eneg else 0.0

def evaluate_claim(claim: str, evidence_texts: list[str]) -> dict:
    best_support = 0.0
    best_contra = 0.0
    matched = 0

    for ev in evidence_texts:
        for chunk in SENTENCE_RE.split(ev[:15000]):
            sim = _similarity(claim, chunk)
            if sim < 0.10:
                continue
            matched += 1
            flip = _negation_flip(claim, chunk)
            support = sim * (1.0 - 0.65 * flip)
            contra = sim * (0.35 + 0.65 * flip)
            best_support = max(best_support, support)
            best_contra = max(best_contra, contra)

    if matched == 0:
        verdict = "INSUFFICIENT_EVIDENCE"
    elif best_support >= 0.32 and best_support > best_contra * 1.25:
        verdict = "SUPPORTED"
    elif best_contra >= 0.32 and best_contra > best_support * 1.25:
        verdict = "CONTRADICTED"
    else:
        verdict = "MIXED"

    return {
        "claim": claim,
        "support_score": round(min(best_support, 1.0), 3),
        "contradiction_score": round(min(best_contra, 1.0), 3),
        "matched_evidence": matched,
        "verdict": verdict,
    }

def aggregate(results: list[dict]) -> tuple[str, float]:
    if not results:
        return "INSUFFICIENT_EVIDENCE", 0.0

    counts = {k: 0 for k in ("SUPPORTED","CONTRADICTED","MIXED","INSUFFICIENT_EVIDENCE")}
    signal = []
    for r in results:
        counts[r["verdict"]] += 1
        signal.append(max(r["support_score"], r["contradiction_score"]))

    decisive = counts["SUPPORTED"] + counts["CONTRADICTED"]
    if decisive == 0:
        verdict = "MIXED" if counts["MIXED"] else "INSUFFICIENT_EVIDENCE"
    elif counts["SUPPORTED"] >= math.ceil(len(results) * 0.6) and counts["CONTRADICTED"] == 0:
        verdict = "SUPPORTED"
    elif counts["CONTRADICTED"] >= math.ceil(len(results) * 0.6) and counts["SUPPORTED"] == 0:
        verdict = "CONTRADICTED"
    else:
        verdict = "MIXED"

    coverage = 1 - (counts["INSUFFICIENT_EVIDENCE"] / len(results))
    strength = sum(signal) / len(signal)
    confidence = max(0.0, min(0.95, (coverage * 0.55) + (strength * 0.45)))
    return verdict, round(confidence, 3)
