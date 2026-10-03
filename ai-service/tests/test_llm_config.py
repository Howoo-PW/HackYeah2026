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
