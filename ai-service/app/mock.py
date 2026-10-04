"""Fixed responses for MOCK_AI=true, matching the examples in docs/CONTRACT.md."""

from .schemas import SummaryContent, SurfaceOut

MOCK_MODEL = "mock"

MOCK_SUMMARY = SummaryContent(
    surface="Nowy asfalt od mostu, dziury przy skrzyżowaniu.",
    views="Piękny widok na Wawel.",
    safety="brak informacji",
    traffic="Wieczorem korki.",
    parking="Trudno zaparkować.",
    overall="Ładna, ale zatłoczona trasa.",
    confidence="medium",
    conflicts=[],
)

MOCK_SURFACE = SurfaceOut(surface="asphalt", condition=3, potholes=True, cracks=False, confidence="medium")


def mock_embedding(text: str) -> list[float]:
    """Deterministic stand-in for MOCK_AI: hashed bag of words, so texts sharing words are close (no meaning, no network)."""
    import hashlib
    import math
    import re

    vec = [0.0] * 1536
    for word in re.findall(r"\w+", text.lower()):
        h = int.from_bytes(hashlib.sha256(word[:6].encode()).digest()[:4], "big")
        vec[h % 1536] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
