from app.engine import aggregate, evaluate_claim, extract_claims

def test_claim_extraction():
    claims = extract_claims(
        "El ayuntamiento aprobó la medida el martes. "
        "La resolución fue publicada oficialmente el miércoles."
    )
    assert len(claims) == 2

def test_insufficient_without_evidence():
    r = evaluate_claim("El ayuntamiento aprobó la medida el martes.", [])
    assert r["verdict"] == "INSUFFICIENT_EVIDENCE"

def test_aggregate_insufficient():
    verdict, confidence = aggregate([{
        "verdict": "INSUFFICIENT_EVIDENCE",
        "support_score": 0.0,
        "contradiction_score": 0.0
    }])
    assert verdict == "INSUFFICIENT_EVIDENCE"
    assert confidence == 0.0
