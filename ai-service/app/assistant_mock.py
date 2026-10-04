"""Assistant with MOCK_AI=true: a small rule-based reader of Polish requests, so the feature works without a model.

It does not decline words ("z Rynku Głównego" stays inflected), so it is good for demos and tests, not for real use.
"""

import re

from .assistant_schemas import AnswerRequest, AssistantPlan, PlanWeights

_PROFILES = (
    ("cycling-regular", ("rower", "rowerem", "rowerze", "rowerow")),
    ("foot-walking", ("pieszo", "na piechotę", "spacer", "na nogach")),
    ("driving-car", ("samochod", "autem", "dojechać", "jechać")),
)
_WEIGHT_WORDS = {
    "views": ("widok", "ładn", "piękn", "malown", "krajobraz"),
    "surface": ("nawierzchni", "równ", "gładk", "dziur", "asfalt"),
    "safety": ("bezpiecz", "oświetl"),
    "traffic": ("spokojn", "cich", "korek", "mało samochod", "mały ruch", "bez ruchu", "mało ruchu"),
}
# superlative -> (dimension, which end)
_RANKING = (
    ("najładniejsz", "views", "best"), ("najpiękniejsz", "views", "best"), ("najlepsze widoki", "views", "best"),
    ("najrówniejsz", "surface", "best"), ("najlepsza nawierzchni", "surface", "best"), ("najgorsza nawierzchni", "surface", "worst"),
    ("najbezpieczniejsz", "safety", "best"), ("najniebezpieczniejsz", "safety", "worst"),
    ("najspokojniejsz", "traffic", "best"), ("najcichsz", "traffic", "best"), ("najbardziej zakorkowan", "traffic", "worst"),
)
# where a place name ends: before one of these words or at punctuation
_END = r"(?=\s+(?:przez|z|ze|i|bez|omijaj|omijając|unikaj|unikając|żeby|aby|która|który|rowerem|samochodem|autem|pieszo|szybko|spokojnie)\b|[,.;!?]|$)"


def _clean(text: str | None) -> str | None:
    text = (text or "").strip(" .,;!?\"'")
    return text or None


def mock_plan(query: str) -> AssistantPlan:
    """Reads a Polish request with keyword rules: route (z A do B), streets (najładniejsze ... na X), place (pokaż X)."""
    low = query.lower().strip()
    profile = next((p for p, words in _PROFILES if any(w in low for w in words)), "driving-car")
    weights = PlanWeights(**{dim: 3 for dim, words in _WEIGHT_WORDS.items() if any(w in low for w in words)})

    route = re.search(rf"\b(?:z|od)\s+(?P<a>.+?)\s+(?:do|na)\s+(?P<b>.+?){_END}", low)
    if route and _clean(route["a"]) and _clean(route["b"]):
        via = re.search(r"\bprzez\s+(?P<v>.+?)(?=[,.;!?]|\s+(?:z|i|bez|rowerem|samochodem|autem|pieszo)\b|$)", low)
        return AssistantPlan(
            intent="route",
            restated=f"Trasa z {_clean(route['a'])} do {_clean(route['b'])}.",
            from_place=_clean(route["a"]),
            to_place=_clean(route["b"]),
            via_places=[_clean(via["v"])] if via and _clean(via["v"]) else [],
            profile=profile,
            weights=weights,
        )

    for stem, dimension, want in _RANKING:
        if stem in low:
            rest = low.split(stem, 1)[1]
            area = re.search(r"\b(?:na|w|we|okolicy|dzielnicy|rejonie)\s+(?:okolicy\s+|dzielnicy\s+)?(?P<a>[\wąćęłńóśźż -]+?)(?=[,.;!?]|$)", rest)
            return AssistantPlan(
                intent="streets",
                restated=f"Szukam ulic: {'najlepszych' if want == 'best' else 'najgorszych'} pod względem kryterium {dimension}.",
                dimension=dimension,
                want=want,
                area=_clean(area["a"]) if area else None,
                profile=profile,
            )

    place = re.search(r"(?:pokaż|pokaz|znajdź|znajdz|gdzie jest|gdzie znajduje się|gdzie leży)\s+(?P<p>.+)", low)
    if place and _clean(place["p"]):
        return AssistantPlan(intent="place", restated=f"Pokazuję miejsce: {_clean(place['p'])}.", place_query=_clean(place["p"]))

    return AssistantPlan(intent="unsupported", restated="Nie rozumiem, o jaką trasę lub miejsce chodzi.")


def mock_answer(req: AnswerRequest) -> str:
    """A plain reply that strings the facts together (no model involved)."""
    lead = {"route": "Wyznaczyłem trasę.", "place": "Znalazłem to miejsce.", "streets": "Oto ulice, które pasują."}[req.intent]
    return " ".join([lead, *req.facts[:4]])
