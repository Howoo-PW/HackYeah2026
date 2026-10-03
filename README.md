# Rate Your Ride

Ocenianie odcinków dróg w Krakowie: nawierzchnia, widoki, bezpieczeństwo, ruch, parkingi. HackYeah 2026.

Plan: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · Kontrakt API: [docs/CONTRACT.md](docs/CONTRACT.md) · Mapy: [docs/MAP_STACK.md](docs/MAP_STACK.md)

## Uruchomienie

Wymagany Docker Desktop (uruchomiony).

```bash
cp .env.example .env          # uzupełnij klucze (dane od zespołu)
docker compose up --build
```

| Usługa | Adres | Kod |
|---|---|---|
| Frontend | http://localhost:5173 | `frontend/` (React, Vite, TS, Tailwind) |
| Backend | http://localhost:8000/api/v1/health, dokumentacja: http://localhost:8000/docs | `backend/` (FastAPI) |
| Serwis AI | http://localhost:8001/health | `ai-service/` (FastAPI) |

Zmiany w kodzie przeładowują się automatycznie. Po zmianie `requirements.txt` lub `package.json`: `docker compose up --build`.

Baza danych to Supabase online — lokalnej bazy nie ma.

## B1 — backend i diagnostyka

Implementacja B1 na osobnym branchu `backend/b1-howoo`.
Uruchomienie i testy: [backend/README.md](backend/README.md).
Analiza branchy i dalsza integracja: [docs/B1_HANDOFF.md](docs/B1_HANDOFF.md).

```bash
python scripts/verify_env.py --skip-services # diagnostyka przed uruchomieniem
python scripts/verify_env.py --start         # budowa i start Compose, potem health
python scripts/create_dev_admin.py          # tylko APP_ENV=dev, dane w .env
```

Diagnostyka nie wypisuje wartości kluczy. Puste zmienne opcjonalne (np.
AI_API_KEY przy MOCK_AI=true) są dozwolone. Brak konfiguracji DB oznacza
health 503/down; frontend czeka na sprawny backend.
Supabase MCP w `.mcp.json` działa read-only i wymaga osobistego OAuth przez `/mcp`.
