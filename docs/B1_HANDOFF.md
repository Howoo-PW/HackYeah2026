# B1 — wykonanie i dalsza konfiguracja

Branch użytkownika: `backend/b1-howoo`, opublikowany na origin.
Pierwszy commit B1: `4bfdf0a`, integracja Redis/CI: `fbc4321`.
Draft do przeglądu: [PR #2](https://github.com/Howoo-PW/HackYeah2026/pull/2).
Scalono branche mapy, AI, routingu i migracje B2. Kod B1 pozostaje poza main.

## Zrealizowane kroki

| Punkt | Wynik |
|---|---|
| 1. Konfiguracja | Publiczne klucze Supabase w ignorowanym .env; INTERNAL_API_KEY wygenerowany. Hasło DB i service_role odroczone na prośbę użytkownika. |
| 2. Uruchomienie | Redis, mapa, backend i AI działają w kontenerach. Mapa, AI i trasy korzystają z danych demonstracyjnych. Seed online wymaga wskazania konta Supabase. |
| 3. Testy | 70 testów backendu, 10 AI, frontend build/lint PASS. HTTP: 3 trasy mock i podsumowanie 5 komentarzy. GitHub Actions na fbc4321: PASS. Realne zapisy DB odroczone bez sekretów. |
| 4. MCP | Context7 initialize/tools/list PASS; plugin Supabase działa. Bezpośredni Supabase MCP wymaga osobistego OAuth. |
| 5. Integracja | FE, AI, routing i migracje B2 połączone na branchu B1; zachowano JWT, transakcje i wspólne błędy. |
| 6. Wiele procesów | Limiter Redis z atomowym Lua, TTL i trwałym wolumenem; test równoczesnych klientów PASS. Routing 30/min na IP. |
| 7. Ochrona main | Ustawiona i potwierdzona: PR, 1 akceptacja, checki backend/ai/frontend, zakaz force-push/usunięcia; także dla administratorów. |

Konfiguracja: [.github/main-protection.json](../.github/main-protection.json).
Wynik CI: [GitHub Actions](https://github.com/Howoo-PW/HackYeah2026/actions/runs/37140097666).

## Dostęp lokalny

- Mapa: http://localhost:5173
- API: http://localhost:8000/docs
- AI health: http://localhost:8001/health
- Redis projektu: localhost:16379 (6379 zajęty przez inną usługę).

Bez SUPABASE_DB_URL backend health prawidłowo zwraca HTTP 503/down.
Frontend pokazuje dane demonstracyjne. Normalnie Compose czeka ze startem
frontendu na zdrową bazę; demo uruchomiono osobno przez
`docker compose up -d --no-deps frontend`.

## Brakujące dane

Użytkownik wybrał kontynuowanie bez kluczy. Do pełnej integracji potrzebne są:

- SUPABASE_DB_URL: URL poolera z hasłem PostgreSQL, SSL wymagany.
- SUPABASE_SERVICE_ROLE_KEY: wyłącznie backend/Storage i skrypt administratora.
- DEV_ADMIN_EMAIL i DEV_ADMIN_PASSWORD: konto dev do rzeczywistej próby Auth.
- ORS_API_KEY dla ROUTING_PROVIDER=ors; obecnie wybrano mock.

Plugin Supabase nie udostępnia hasła DB ani service_role.
Oba konta (Supabase i Primary) widzą ten sam projekt; przed zapisami
narzędzia wymagają wskazania konta. Nie zmieniano zdalnych danych ani Auth.

Po uzupełnieniu sekretów: `python scripts/verify_env.py --start`, seed B2,
próba loginu, ocena 201/200, komentarz, moderacja i odświeżenie mapy.
Kontrakt API bez zmian. Sekrety i rola lokalna ignorowane przez git.
