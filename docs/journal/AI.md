# Dziennik AI — serwis AI + backend

Najnowsze wpisy na górze. Szablon: [README.md](README.md).

<!-- wpisy -->

## 2026-10-03 — prukasz — gałąź `setup/docker`

**Zadanie:** postawić Docker Compose ze szkieletami wszystkich usług, zanim zespół zacznie pracę.

**Zrobione:**
- `docker-compose.yml`: frontend (5173), backend (8000), ai (8001→8000), healthchecki, hot reload
- szkielety: backend `/api/v1/health` (sprawdza AI), ai `/health` (tryb mock), frontend Vite + React + TS + Tailwind z ekranem stanu usług
- `.env.example`, `README.md`; sprawdzone: wszystkie kontenery healthy, CORS, build frontendu, przeładowanie po zmianie kodu

**Dalej / blokery:**
- PR `setup/docker` → `main`, potem gałąź `ai/service`: `/summarize` (mock → LangChain)
