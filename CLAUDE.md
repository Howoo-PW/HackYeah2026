# Rate My Road — instrukcje dla Claude

Aplikacja do oceniania odcinków dróg w Krakowie. Zespół 4 osób, hackathon HackYeah 2026.

Przed każdą pracą załaduj `.claude/skills/project-overview/SKILL.md`,
a potem skill obszaru (`backend`, `database`, `ai`, `frontend`).
Są w `.claude/skills/`. Globalny stan i TODO prowadź w overview.

Po zmianie kodu dodaj docstringi/JSDoc publicznych funkcji, zaktualizuj strukturę,
Stan i TODO skilla obszaru i overview oraz dziennik swojej roli.

## Najpierw przeczytaj

- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — architektura, dane, bezpieczeństwo, gałęzie, etapy
- [docs/CONTRACT.md](docs/CONTRACT.md) — jedyne źródło prawdy dla API, typów, enumów, portów. Nie zmieniaj go przy okazji: osobny PR
- [docs/MAP_STACK.md](docs/MAP_STACK.md) — biblioteki i usługi mapowe

## Start każdej sesji

Hook `SessionStart` podaje, kto pracuje (z `.claude/role.local.json`) i stan gita.

1. Jeśli rola nie jest znana z wiadomości ani pliku lokalnego — zapytaj o imię i rolę (FE / B1 / B2 / AI) i zapisz do `.claude/role.local.json`.
2. Zapytaj, nad czym osoba teraz pracuje (zadanie, gałąź), chyba że pierwsza wiadomość to mówi.
3. Sprawdź stan gita: `git status`, `git fetch`, aktualna gałąź. Na `main` nie pracujemy — przełącz na gałąź z sekcji 7 planu albo zapytaj.
4. Dodaj wpis w dzienniku tej osoby (niżej).

## Dziennik pracy

Każda rola ma swój plik: `docs/journal/FE.md`, `B1.md`, `B2.md`, `AI.md`. Piszesz **tylko** w dzienniku osoby, z którą pracujesz.

- Na starcie zadania dopisz na górze (najnowsze pierwsze) wpis z szablonu z [docs/journal/README.md](docs/journal/README.md).
- Po skończeniu zadania lub przed końcem sesji uzupełnij „Zrobione” i „Dalej / blokery”.
- Dziennik commituj razem z pracą na tej samej gałęzi.

## Zasady

- Odpowiadaj po polsku. Kod, nazwy i komentarze w kodzie po angielsku.
- Sekrety tylko w `.env`, nigdy w repo, promptach ani logach.
- Commit i push tylko na prośbę osoby. Do `main` tylko przez PR.
- Bez atrybucji Claude w commitach i PR-ach.
- Dokumentację bibliotek bierz z Context7 (MCP), nie z pamięci.
- Supabase: zmiany schematu tylko jako pliki w `supabase/migrations/`, nawet jeśli stosujesz je przez MCP.
