# Rate My Road — start dla jury

## Uruchomienie

Potrzebujesz uruchomionego **Docker Desktop z kontenerami Linux i Docker Compose
v2.20+**, połączenia z internetem oraz wolnych portów 5173, 8000 i 8001.
Cała aplikacja uruchamia się lokalnie; baza Supabase, logowanie, zdjęcia, AI
i kafelki mapy korzystają z usług online zespołu.

1. Rozpakuj `RateMyRoad-jury.zip`.
2. Otwórz terminal w rozpakowanym folderze `RateMyRoad`.
3. Wykonaj jedną komendę (PowerShell, cmd, macOS lub Linux):

```sh
docker compose --env-file .env -f docker-compose.jury.yml up --build --wait --wait-timeout 180
```

4. Otwórz **http://localhost:5173**.

`.env` jest już skonfigurowany i dołączony do paczki. Nie kopiuj na niego
`.env.example`. Nie trzeba instalować Node.js, Pythona ani Supabase CLI,
tworzyć projektu Supabase, importować danych ani uruchamiać migracji.

Pierwsza budowa obrazów może potrwać kilka minut. Limit 180 sekund dotyczy
oczekiwania na gotowość usług po zbudowaniu obrazów. Komenda uruchamia
frontend, backend, serwis AI i Redis w tle i czeka na wszystkie usługi.
Backend musi potwierdzić dostęp do bazy, grafu tras i serwisu AI.
Tryb jury korzysta z prawdziwego AI i nie wymusza danych mockowych.

## Ocena projektu

Scenariusz testów z oczekiwanymi wynikami:
[jury/SCENARIUSZ_OCENY.md](jury/SCENARIUSZ_OCENY.md).

| Materiał | Plik |
|---|---|
| Krótki opis pomysłu | [docs/brief-short.md](docs/brief-short.md) |
| Problem i rozwiązanie | [submission/problem.md](submission/problem.md), [submission/solution.md](submission/solution.md) |
| Opis projektu | [docs/brief.md](docs/brief.md) |
| API i model danych | [docs/CONTRACT.md](docs/CONTRACT.md) |
| Algorytm tras | [docs/ROUTING_GRAPH.md](docs/ROUTING_GRAPH.md) |
| Asystent AI | [docs/ASSISTANT.md](docs/ASSISTANT.md) |
| Źródła aplikacji | `frontend/`, `backend/`, `ai-service/` |
| Schemat i dane startowe | `supabase/` |
| Commit źródeł paczki | `jury/BUILD.json` |

Źródła są pobierane bezpośrednio z commita `origin/main` zapisanego w
`jury/BUILD.json`. Dodatkowe pliki dla jury to konfiguracja Docker Compose,
pliki w `jury/` i niniejsza instrukcja.

## Diagnostyka i zatrzymanie

Stan aplikacji: http://localhost:8000/api/v1/health (`status: ok`).
Dokumentacja interaktywna API: http://localhost:8000/docs.
Stan AI: http://localhost:8001/health (`mock: false`).

Stan kontenerów i logi:

```sh
docker compose --env-file .env -f docker-compose.jury.yml ps
docker compose --env-file .env -f docker-compose.jury.yml logs --tail 80
```

Jeśli port jest zajęty, zatrzymaj poprzednią instancję aplikacji lub program,
który używa tego portu, i wykonaj ponownie komendę startową. Jeśli usługa
pozostaje `unhealthy`, sprawdź internet oraz logi odpowiedniego kontenera.

Zatrzymanie aplikacji:

```sh
docker compose --env-file .env -f docker-compose.jury.yml down
```

Oceny, opinie i zdjęcia są zapisywane w Supabase online. Zatrzymanie lokalnych
kontenerów nie usuwa tych danych. Rejestracja i zapis wymagają usług zespołu
dostępnych podczas oceny.

## Odtworzenie ZIP-a przez zespół

W repo po aktualizacji referencji `origin/main` wykonaj:

```sh
python jury/package.py
```

Wynik: `submission/jury/RateMyRoad-jury.zip`. Skrypt pakuje wyłącznie źródła
z commita `origin/main`, konfigurację jury oraz bieżący `.env`. ZIP nie zawiera
historii Git, lokalnych zależności ani niezacommitowanych zmian aplikacji.
Wynik jest lokalnie ignorowany przez Git.

Paczka zawiera sekrety usług — przekaż ją prywatnie jury. Publiczne repo
zawiera kod; plik `.env` i ZIP służą do prywatnego uruchomienia demonstracji.
