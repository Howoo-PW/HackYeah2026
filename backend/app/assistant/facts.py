"""Facts for the assistant's answer, as plain Polish sentences built from database rows (docs/ASSISTANT.md).

Scores are turned into words on purpose: the model is told not to quote numbers, and words are what a person would say.
Comments are user text: they are cleaned of angle brackets so they cannot close the <facts> block the model reads.
"""

import re

DIMENSIONS = ("surface", "views", "safety", "traffic", "parking")
LABELS = {"surface": "nawierzchnia", "views": "widoki", "safety": "bezpieczeństwo", "traffic": "ruch", "parking": "parking"}
# 5 is always the best; for traffic that means calm. Five bands: <1.75, <2.5, <3.5, <4.25, the rest.
WORDS = {
    "traffic": ("bardzo duży", "duży", "umiarkowany", "spokojny", "bardzo spokojny"),
    "parking": ("bardzo trudny", "trudny", "przeciętny", "łatwy", "bardzo łatwy"),
    "default": ("bardzo słaba", "słaba", "przeciętna", "dobra", "bardzo dobra"),
}
WORDS["views"] = ("brzydkie", "mało ciekawe", "przeciętne", "ładne", "piękne")
WORDS["safety"] = ("bardzo niebezpiecznie", "niebezpiecznie", "przeciętnie", "bezpiecznie", "bardzo bezpiecznie")
OBSTACLES = {"roadwork": "remont", "closure": "zamknięcie drogi", "pothole": "dziura", "accident": "wypadek", "other": "utrudnienie"}
UNNAMED = "bez nazwy"  # what the database query calls a road piece without a name
PROFILE_NAMES = {"driving-car": "samochodem", "cycling-regular": "rowerem", "foot-walking": "pieszo"}


def score_word(dimension: str, value: float) -> str:
    """A 1-5 score as a word fitting the dimension ("dobra", "spokojny", "ładne")."""
    band = 0 if value < 1.75 else 1 if value < 2.5 else 2 if value < 3.5 else 3 if value < 4.25 else 4
    return WORDS.get(dimension, WORDS["default"])[band]


def scores_text(scores: dict, dimensions: tuple[str, ...] = DIMENSIONS) -> str:
    """"nawierzchnia: dobra; widoki: ładne" for the dimensions that have a score; an empty string when none do."""
    return "; ".join(f"{LABELS[d]}: {score_word(d, scores[d])}" for d in dimensions if scores.get(d) is not None)


def ratings_word(count: int) -> str:
    """How much evidence there is, in words (the model must not quote counts)."""
    if count <= 0:
        return "bez własnych ocen użytkowników (wynik szacowany z podobnych odcinków)"
    return "oceniona przez niewielu użytkowników" if count < 3 else "oceniona przez kilku użytkowników" if count < 10 else "oceniona przez wielu użytkowników"


def clean(text: str, limit: int = 220) -> str:
    """User text on one line, without angle brackets, shortened."""
    text = re.sub(r"[<>]", " ", " ".join((text or "").split()))
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def distance_text(meters: float) -> str:
    return f"{round(meters)} m" if meters < 1000 else f"{meters / 1000:.1f}".replace(".", ",") + " km"


def duration_text(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60} min"


def street_fact(info: dict, on_route: bool = True) -> str:
    """One street (or fragment): how long (the part of the route it makes up, when `on_route`) and how it is rated."""
    name = info["name"]
    length = f" (około {distance_text(info['length_m'])}{' trasy' if on_route else ''})" if info.get("length_m") else ""
    rated = scores_text(info, DIMENSIONS[:4] if on_route else DIMENSIONS)  # routes are not planned around parking
    kind = "Droga bez nazwy" if name == UNNAMED else f"Ulica {name}"
    return f"{kind}{length}: {rated or 'brak ocen'}; {ratings_word(info.get('ratings', 0))}."


def comment_fact(day, text: str) -> str:
    return f"Komentarz użytkownika z {day}: „{clean(text)}”"


def summary_fact(overall: str) -> str:
    return f"Podsumowanie opinii (AI): {clean(overall, 300)}"


def obstacle_fact(kind: str, description: str | None, valid_until) -> str:
    until = f", do {valid_until:%Y-%m-%d}" if valid_until else ""
    detail = f": {clean(description, 160)}" if description else ""
    return f"Aktywna przeszkoda na trasie: {OBSTACLES.get(kind, 'utrudnienie')}{detail}{until}."


def route_facts(main: dict, fastest: dict | None, profile: str, weights: dict, start: str, end: str, via: list[str]) -> list[str]:
    """What the route is, how it was chosen and how it compares with the fastest one."""
    wanted = [LABELS[d] for d, w in weights.items() if w and d in LABELS]
    facts = [
        f"Trasa {PROFILE_NAMES[profile]} z {start} do {end}" + (f" przez {', '.join(via)}" if via else "")
        + f": {distance_text(main['distance_m'])}, około {duration_text(main['duration_s'])}.",
        "Trasę wybrano pod kątem: " + (", ".join(wanted) + "." if wanted else "najkrótszego czasu przejazdu (użytkownik nie podał preferencji)."),
    ]
    scores = scores_text(main["scores"], DIMENSIONS[:4])
    if scores:
        facts.append(f"Oceny użytkowników wzdłuż trasy: {scores}. Oceny obejmują około {round(main['coverage'] * 100)}% jej długości.")
    else:
        facts.append("Wzdłuż tej trasy nie ma jeszcze ocen użytkowników.")
    if fastest:
        extra = main["duration_s"] - fastest["duration_s"]
        facts.append(
            f"Najszybsza trasa jest krótsza o około {duration_text(abs(extra))} ({distance_text(fastest['distance_m'])})." if extra > 30
            else "Wybrana trasa jest praktycznie tak samo szybka jak najszybsza."
        )
    return facts
