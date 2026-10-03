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
