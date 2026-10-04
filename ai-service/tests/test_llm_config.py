"""Model call configuration that needs no network: schema hint and structured-output method."""

import json

from app import llm
from app.config import settings
from app.schemas import SummaryContent, SurfaceOut


def test_schema_hint_lists_every_key_with_placeholders_and_descriptions():
    hint = llm.schema_hint(SummaryContent)
    example = json.loads(hint.split("kluczami:\n")[1].split("\nOpisy pól:")[0])
    assert set(example) == set(SummaryContent.model_fields)
    assert example["confidence"] == "low|medium|high"
    assert example["conflicts"] == "lista tekstów" and example["overall"] == "tekst"
    assert "brak informacji" in hint  # the field descriptions travel with it
    assert "WYŁĄCZNIE" in hint


def test_schema_hint_for_the_surface_schema():
    example = json.loads(llm.schema_hint(SurfaceOut).split("kluczami:\n")[1].split("\nOpisy pól:")[0])
    assert example["condition"] == "liczba" and example["potholes"] == "true/false"


class FakeModel:
    def __init__(self):
        self.calls = []

    def with_structured_output(self, schema, **kwargs):
        self.calls.append(kwargs)
        return self


def test_json_mode_puts_the_schema_in_the_prompt(monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(llm, "_model", lambda: fake)
    monkeypatch.setattr(settings, "ai_structured_method", "json_mode")
    _, system = llm._structured(SummaryContent, "PROMPT")
    assert fake.calls == [{"method": "json_mode"}]
    assert system.content.startswith("PROMPT") and "WYŁĄCZNIE" in system.content


def test_default_method_leaves_the_prompt_alone(monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(llm, "_model", lambda: fake)
    monkeypatch.setattr(settings, "ai_structured_method", None)
    _, system = llm._structured(SummaryContent, "PROMPT")
    assert fake.calls == [{}] and system.content == "PROMPT"


def _captured_model_kwargs(monkeypatch, **overrides):
    seen = {}
    monkeypatch.setattr(llm, "init_chat_model", lambda name, **kwargs: seen.update(name=name, **kwargs) or object())
    llm._model.cache_clear()
    for key, value in {"ai_model": "m", "ai_provider": "openai", "ai_api_key": "k", "ai_base_url": None,
                       "ai_reasoning_effort": None, **overrides}.items():
        monkeypatch.setattr(settings, key, value)
    try:
        llm._model()
    finally:
        llm._model.cache_clear()
    return seen


def test_native_openai_reasoning_model_gets_effort_and_no_temperature(monkeypatch):
    seen = _captured_model_kwargs(monkeypatch, ai_model="gpt-5-nano", ai_reasoning_effort="minimal")
    assert seen["reasoning_effort"] == "minimal"
    assert "temperature" not in seen and "extra_body" not in seen


def test_gateway_reasoning_uses_extra_body_and_keeps_temperature(monkeypatch):
    seen = _captured_model_kwargs(monkeypatch, ai_base_url="https://openrouter.ai/api/v1", ai_reasoning_effort="low")
    assert seen["extra_body"] == {"reasoning": {"effort": "low"}} and seen["temperature"] == 0
    assert "reasoning_effort" not in seen


def test_plain_model_gets_temperature_zero_only(monkeypatch):
    seen = _captured_model_kwargs(monkeypatch)
    assert seen["temperature"] == 0 and "reasoning_effort" not in seen and "extra_body" not in seen


def test_user_message_pairs_average_scores_with_each_authors_own_scores():
    from app.schemas import SummarizeRequest

    req = SummarizeRequest(
        segment_id=1,
        ratings_count=6,
        scores={"surface": 4.06, "views": None, "safety": 3, "traffic": 2.91, "parking": None},
        comments=[
            {"id": "a", "text": "Gładki asfalt.", "created_at": "2026-10-01T10:00:00Z", "rating": {"surface": 5, "traffic": 3}},
            {"id": "b", "text": "Bez oceny.", "created_at": "2026-10-02T10:00:00Z"},
        ],
    )
    text = llm.build_user_message(req)
    assert "Średnie oceny z 6 ocen: nawierzchnia 4.1, bezpieczeństwo 3.0, ruch (5 = mały) 2.9" in text
    assert "- [2026-10-01] (oceny autora: nawierzchnia 5.0, ruch (5 = mały) 3.0) Gładki asfalt." in text
    assert "- [2026-10-02] Bez oceny." in text  # no scores, no brackets
    assert text.index("<ratings>") < text.index("<comments>")


def test_user_message_without_ratings_has_only_comments():
    from app.schemas import SummarizeRequest

    req = SummarizeRequest(segment_id=1, comments=[{"id": "a", "text": "Dziury.", "created_at": "2026-10-01T10:00:00Z"}])
    assert "<ratings>" not in llm.build_user_message(req)


def test_user_message_mentions_attached_photos():
    from app.schemas import SummarizeRequest

    req = SummarizeRequest(segment_id=1, image_urls=["https://x/y.jpg"], comments=[{"id": "a", "text": "Dziury.", "created_at": "2026-10-01T10:00:00Z"}])
    assert "nie udało się ich przeanalizować" in llm.build_user_message(req)  # photos but no analysis
    note = llm.describe_photo(1, SurfaceOut(surface="asfalt", condition=2, potholes=False, cracks=True, confidence="medium"))
    assert note == "- zdjęcie 1: nawierzchnia asfalt, stan zły, pęknięcia: tak, dziury: nie, pewność analizy: średnia"
    message = llm.build_user_message(req, [note])
    assert "Analiza zdjęć drogi" in message and note in message and message.index("<photos>") < message.index("<comments>")


def test_photo_urls_must_be_https():
    import pytest
    from pydantic import ValidationError

    from app.schemas import SummarizeRequest

    comments = [{"id": "a", "text": "Dziury.", "created_at": "2026-10-01T10:00:00Z"}]
    with pytest.raises(ValidationError):
        SummarizeRequest(segment_id=1, image_urls=["http://insecure/y.jpg"], comments=comments)
    with pytest.raises(ValidationError):
        SummarizeRequest(segment_id=1, image_urls=["https://x/1.jpg"] * 5, comments=comments)


def test_prompt_has_no_rating_rules_when_the_request_has_no_ratings():
    from app.schemas import SummarizeRequest

    req = SummarizeRequest(segment_id=1, comments=[{"id": "a", "text": "Dziury.", "created_at": "2026-10-01T10:00:00Z"}])
    assert not llm.has_ratings(req)
    prompt = llm.summary_prompt(req)
    assert "Nie masz ocen liczbowych" in prompt and "skali 1-5" not in prompt and "{" not in prompt


def test_prompt_keeps_the_rating_rules_when_ratings_are_sent():
    from app.schemas import SummarizeRequest

    req = SummarizeRequest(segment_id=1, ratings_count=3, scores={"surface": 4.0},
                           comments=[{"id": "a", "text": "Dziury.", "created_at": "2026-10-01T10:00:00Z"}])
    assert llm.has_ratings(req)
    prompt = llm.summary_prompt(req)
    assert "skali 1-5" in prompt and "NIGDY nie podawaj" in prompt and "{" not in prompt


def test_prompt_talks_about_photos_only_when_they_are_attached():
    from app.schemas import SummarizeRequest

    comments = [{"id": "a", "text": "Dziury.", "created_at": "2026-10-01T10:00:00Z"}]
    without = llm.summary_prompt(SummarizeRequest(segment_id=1, comments=comments))
    with_photos = llm.summary_prompt(SummarizeRequest(segment_id=1, comments=comments, image_urls=["https://x/1.jpg"]))
    assert "DOŁĄCZONO ANALIZĘ ZDJĘĆ" not in without and "oraz zdjęcia drogi" not in without
    assert "DOŁĄCZONO ANALIZĘ ZDJĘĆ" in with_photos and "oraz zdjęcia drogi" in with_photos and "{" not in with_photos


def test_a_photo_alone_is_enough_but_nothing_at_all_is_not():
    import pytest
    from pydantic import ValidationError

    from app.schemas import SummarizeRequest

    req = SummarizeRequest(segment_id=1, image_urls=["https://x/1.jpg"])
    assert req.comments == []
    assert "Brak komentarzy" in llm.build_user_message(req)
    with pytest.raises(ValidationError):
        SummarizeRequest(segment_id=1)
