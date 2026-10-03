# Serwis AI — Rate My Road

FastAPI + LangChain. Właściciel: AI. Kontrakt: [../docs/CONTRACT.md](../docs/CONTRACT.md), sekcja 6. Serwis wewnętrzny — woła go tylko backend z nagłówkiem `X-Internal-Key`.

| Endpoint | Opis |
|---|---|
| `GET /health` | Stan, dostawca, model, tryb mock |
| `POST /summarize` | Podsumowanie 1–50 komentarzy odcinka |
| `POST /analyze-surface` | Ocena nawierzchni ze zdjęć (opcjonalne) |

## Konfiguracja (`.env` w katalogu głównym)

- `INTERNAL_API_KEY` — wspólny sekret z backendem. Pusty = serwis odrzuca wszystkie żądania.
- `MOCK_AI=true` — stałe odpowiedzi, bez modelu i klucza (domyślnie).
- `MOCK_AI=false` + `AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY` (opcjonalnie `AI_BASE_URL` dla API zgodnych z OpenAI) — prawdziwy model przez LangChain `init_chat_model`. Dla innego dostawcy niż Gemini dodaj jego pakiet `langchain-*` do `requirements.txt`.

Cała obsługa LangChain jest w [app/llm.py](app/llm.py). Błąd dostawcy → `502 UPSTREAM_ERROR`.

## Testy

```bash
docker compose run --rm --no-deps -v ./ai-service:/app ai sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```
