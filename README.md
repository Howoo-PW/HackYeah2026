# Rate My Road

**Oceń drogi jak restauracje.** Rate My Road to mapa dróg, na której użytkownicy oceniają odcinki dróg w pięciu wymiarach (nawierzchnia, widoki, bezpieczeństwo, ruch, parkingi) i piszą opinie ze zdjęciami. Mapa jest kolorowana według ocen, więc od razu widać, które drogi są dobre, a które złe. Sztuczna inteligencja streszcza komentarze, żeby nie trzeba było czytać kilkudziesięciu opinii. Trasę można wyznaczyć w trybie „unikaj złych dróg” albo „wybierz ładną”, z własnymi priorytetami. HackYeah 2026, pilotaż: Kraków.

## Problem

Nawigacja wybiera trasę według czasu i dystansu, a o jakości przejazdu decyduje coś innego. Prowadzi pod adres, a na miejscu w promieniu kilku przecznic wszystkie miejsca parkingowe są zajęte. Kierowca auta z niskim zawieszeniem musi zawracać przed nierówną nawierzchnią i zbyt wysokimi progami zwalniającymi. Nawigacja pokazuje bieżące zdarzenia, ale nie to, gdzie na co dzień jest niebezpiecznie. Motocyklista lub rowerzysta, który chce ładnej trasy, dostaje najszybszą, a przejechanej pięknej drogi nie może polecić innym.

Wiedza o drogach istnieje, ale jest rozproszona po forach i grupach w mediach społecznościowych, szybko się starzeje i nie da się jej oglądać na mapie. Zarządcy dróg nie mają taniego źródła informacji o tym, gdzie jest obiektywnie najgorzej. Dane i źródła: [submission/problem.md](submission/problem.md).

## Rozwiązanie

**Korzyści dla użytkownika:** kierowca niskiego auta omija progi i dziury, motocyklista i rowerzysta wybierają ładne trasy, a każdy może polecić drogę, którą polubił.

**Korzyści dla miasta:** tanie, aktualne dane o stanie dróg i miejscach problemowych, zebrane od mieszkańców, które pomagają ustalać priorytety remontów.

**Społeczność:** wartość aplikacji tworzą jej użytkownicy (community contribution). Mieszkańcy i podróżujący dodają oceny, opinie, zdjęcia i zgłoszenia remontów, a wspólnie budowana mapa jest tym lepsza, im więcej osób do niej dokłada. Tak jak przy opiniach o restauracjach, zaufanie rośnie z liczbą głosów, a stare oceny wygasają, żeby mapa pozostawała aktualna. Społeczność jest też sposobem na rozszerzanie zasięgu: każde nowe miasto zaczyna się od lokalnych użytkowników.

**Zasięg:** Kraków to pilotaż, na którym sprawdzamy pomysł. Docelowo aplikacja ma działać w całej Europie. Mapa i dane dróg pochodzą z OpenStreetMap, które obejmuje cały kontynent, więc rozszerzenie na kolejne miasta nie wymaga zmiany modelu danych.

**Technologia:** React, FastAPI, Supabase (PostGIS), dane OpenStreetMap, serwis AI w osobnym kontenerze, całość w Dockerze.

## Uruchomienie (jedna komenda)

Potrzebujesz Docker Desktop (uruchomionego, kontenery Linux, Compose v2.20+), internetu i wolnych portów 5173, 8000, 8001. Nie instalujesz Node.js ani Pythona i niczego nie konfigurujesz: baza, logowanie, zdjęcia, AI i kafelki mapy działają w usługach online zespołu, a ich konfiguracja jest już w paczce dla jury.

```sh
docker compose --env-file .env -f docker-compose.jury.yml up --build --wait --wait-timeout 180
```

Potem otwórz **http://localhost:5173**. Pierwsza budowa obrazów może potrwać kilka minut. Stan: http://localhost:8000/api/v1/health (`status: ok`). Zatrzymanie: `docker compose --env-file .env -f docker-compose.jury.yml down`. Szczegóły i scenariusz oceny: [JURY.md](JURY.md).

### Bez dołączonej konfiguracji (własne usługi)

Plik `.env` z kluczami nie jest w repozytorium (jest w `.gitignore`), więc jeśli nie dostałeś paczki dla jury, **musisz utworzyć go sam i wpisać własne wartości**. Bez nich komenda zatrzyma się z komunikatem „Uzupelnij … w .env”. Bez własnej bazy aplikacja nie pokaże map ani ocen, bo wszystkie dane są w bazie online.

**1. Utwórz plik `.env` w katalogu głównym repo:**

```sh
cp .env.example .env        # PowerShell: Copy-Item .env.example .env
```

**2. Wpisz własne wartości** (po znaku `=`, bez cudzysłowów i spacji):

| Zmienna | Co wpisać | Skąd to wziąć |
|---|---|---|
| `SUPABASE_URL` | adres projektu, np. `https://abcd.supabase.co` | Supabase → Project Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | klucz publiczny (anon / publishable) | Supabase → Project Settings → API Keys |
| `SUPABASE_SERVICE_ROLE_KEY` | klucz tajny (service_role / secret); tylko backend, nigdy frontend | Supabase → Project Settings → API Keys |
| `SUPABASE_DB_URL` | pełny adres Postgresa z Twoim hasłem bazy (hasło zakoduj jako URL) | Supabase → Connect → Transaction pooler (port 6543) |
| `INTERNAL_API_KEY` | dowolny losowy ciąg, wspólny dla backendu i AI: `python -c "import secrets; print(secrets.token_urlsafe(32))"` | wymyślasz go sam |
| `AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY` | dostawca, model i klucz, np. `openai` / `gpt-5.4-nano` / Twój klucz; dla OpenAI dopisz też `AI_REASONING_EFFORT=none` | konsola Twojego dostawcy AI (wskazówki dla OpenAI i OpenRouter są w `.env.example`) |

Resztę zmiennych zostaw bez zmian. Zmienne `VITE_*` (frontend, publiczne): komenda jury bierze je automatycznie z `SUPABASE_URL` i `SUPABASE_ANON_KEY`, ale w trybie deweloperskim wpisz `VITE_SUPABASE_URL` i `VITE_SUPABASE_ANON_KEY` ręcznie, tymi samymi wartościami (`VITE_API_URL` zostaw bez zmian).

**3. Klucz AI:** komenda jury zawsze używa prawdziwego AI, więc wymaga `AI_MODEL` i `AI_API_KEY`. Jeśli nie masz klucza, uruchom tryb deweloperski (`docker compose up --build`) z `MOCK_AI=true` (wartość domyślna): serwis AI odpowiada wtedy przykładowymi tekstami.

**4. Załaduj schemat i dane do swojej bazy** krok po kroku według [docs/SUPABASE_SETUP.md](docs/SUPABASE_SETUP.md): migracje, odcinki Krakowa, fragmenty ocen, sieć dróg i graf tras, odświeżenie widoków. Ten wariant nie był sprawdzany od zera na pustym projekcie.

**5. Uruchom** komendę z sekcji „Uruchomienie (jedna komenda)” albo tryb deweloperski poniżej. Nigdy nie commituj `.env`.

## Tryb deweloperski

```sh
cp .env.example .env          # i wpisz własne wartości (tabela powyżej)
docker compose up --build     # kod przeładowuje się automatycznie
```

| Usługa | Adres | Kod |
|---|---|---|
| Frontend | http://localhost:5173 | `frontend/` (React, Vite, TypeScript, Tailwind, MapLibre) |
| Backend | http://localhost:8000/api/v1/health, dokumentacja: http://localhost:8000/docs | `backend/` (FastAPI) |
| Serwis AI | http://localhost:8001/health | `ai-service/` (FastAPI) |

Diagnostyka środowiska (bez wypisywania kluczy): `python scripts/verify_env.py --skip-services`. Testy: [backend/README.md](backend/README.md), [scripts/README.md](scripts/README.md).

## Dokumentacja

[Kontrakt API](docs/CONTRACT.md) · [Plan implementacji](IMPLEMENTATION_PLAN.md) · [Opis produktu](docs/brief.md) · [Trasy](docs/ROUTING_GRAPH.md) · [Asystent AI](docs/ASSISTANT.md) · [Mapy](docs/MAP_STACK.md) · [Skrypty](scripts/README.md) · [Dla jury](JURY.md)
