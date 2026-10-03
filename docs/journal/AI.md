# Dziennik AI — serwis AI + backend

Najnowsze wpisy na górze. Szablon: [README.md](README.md).

<!-- wpisy -->

## 2026-10-03 — prukasz — gałąź `ai/service`

**Zadanie:** serwis AI zgodny z kontraktem: `/summarize` i `/analyze-surface`, tryb mock, LangChain.

**Zrobione:**
- endpointy `/health`, `/summarize`, `/analyze-surface`; autoryzacja `X-Internal-Key`; błędy w formacie kontraktu (401, 422, 502)
- tryb mock (domyślny) i ścieżka LangChain (`app/llm.py`, `init_chat_model` + `with_structured_output`), prompt z ochroną przed wstrzykiwaniem poleceń
- 10 testów (pytest w kontenerze) — przechodzą; sprawdzone na żywo w Compose

**Dalej / blokery:**
- wybrać dostawcę i model, dodać klucz do `.env` i przetestować prawdziwe podsumowania po polsku
- integracja w backendzie (`backend/ai-integration`) po `backend/core` od B1

## 2026-10-03 — prukasz — gałąź `setup/docker`

**Zadanie:** postawić Docker Compose ze szkieletami wszystkich usług, zanim zespół zacznie pracę.

**Zrobione:**
- `docker-compose.yml`: frontend (5173), backend (8000), ai (8001→8000), healthchecki, hot reload
- szkielety: backend `/api/v1/health` (sprawdza AI), ai `/health` (tryb mock), frontend Vite + React + TS + Tailwind z ekranem stanu usług
- `.env.example`, `README.md`; sprawdzone: wszystkie kontenery healthy, CORS, build frontendu, przeładowanie po zmianie kodu

**Dalej / blokery:**
- PR `setup/docker` → `main`, potem gałąź `ai/service`: `/summarize` (mock → LangChain)
