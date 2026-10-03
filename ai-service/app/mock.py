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
