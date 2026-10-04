# Asystent AI: trasy i miejsca z opisu

Użytkownik opisuje słowami, czego szuka („rowerem z Rynku Głównego na Wawel, ładne widoki”, „najlepsza nawierzchnia na Podgórzu”,
„pokaż Lokum Salsa”). Aplikacja wyznacza trasę, pokazuje miejsce albo wskazuje ulice, a odpowiedź opiera na **ocenach, komentarzach,
podsumowaniach opinii i przeszkodach z bazy**, nie na wiedzy modelu.

To nie jest „agent” z pętlą narzędzi (plan projektu zabrania agentów i łańcuchów). To przewidywalny potok z dwoma wywołaniami modelu:

```
frontend ──POST /api/v1/assistant──▶ backend
                                       │ 1. POST /assistant/plan   ──▶ serwis AI: opis → plan (route / place / streets)
                                       │ 2. geokodowanie nazw (Nominatim, z cache), trasa z własnego grafu, zapytania do bazy
                                       │ 3. fakty: oceny słowami, komentarze, podsumowania, przeszkody
                                       │ 4. POST /assistant/answer ──▶ serwis AI: fakty → 2–5 zdań odpowiedzi
frontend ◀── trasa / miejsce / ulice + odpowiedź
```

Model nigdy nie dotyka bazy ani nie wymyśla ulic: plan to dane, które backend wykonuje zwykłym kodem, a odpowiedź powstaje wyłącznie z faktów.

## Co potrafi

| Rodzaj (`intent`) | Przykład | Wynik |
|---|---|---|
| `route` | „spokojna trasa rowerowa z Dietla na Nową Hutę, bez dziur” | Trasa(-y) z `POST /route` (profil, wagi i punkty ustawione z opisu), otwierana w planerze; można ją zmienić |
| `place` | „pokaż Lokum Salsa” | Punkt na mapie z kartą miejsca i tym, co dane mówią o drodze obok |
| `streets` | „najładniejsze widoki na Kazimierzu” | Do 5 fragmentów ulic wg kryterium (nawierzchnia, widoki, bezpieczeństwo, ruch, parking) w obrysie dzielnicy, jako numerowane pinezki |
| `clarify` | „jaka będzie pogoda” / nieznane miejsce | Tylko komunikat, co poprawić |

Preferencje użytkownika (`weights` 0–3) model czyta z opisu: „ładne widoki” → `views`, „równa nawierzchnia, bez dziur” → `surface`,
„bezpiecznie” → `safety`, „spokojnie, mało samochodów” → `traffic`; sam czas przejazdu, gdy nic nie wspomniano. Parkingi nie biorą udziału
w trasach (jak w panelu trasy).

## `POST /api/v1/assistant` (backend, publiczny)

Żądanie: `{ "query": "…" }` (3–500 znaków). Limit **10 zapytań/min na IP** (`429 RATE_LIMITED`): każde kosztuje dwa wywołania modelu.

Odpowiedź (`AssistantResponse`):

```ts
{
  intent: "route" | "place" | "streets" | "clarify"
  interpretation: string          // jedno zdanie: co zrozumiano
  answer: string                  // odpowiedź z faktów (po polsku, bez liczb ocen)
  model: string                   // "gpt-…", "mock" albo "fallback" (model nie napisał odpowiedzi: pokazano fakty)
  route: { from, to, via[], profile, weights, routes: RouteOut[] } | null   // routes jak w POST /route
  place: { name, lat, lon, segment_id | null } | null
  streets: { name, group_id, highway, length_m, location, segment_ids[], scores, ratings_count, score }[]
}
```

Błędy: `422` (długość zapytania), `429`, `502 AI_UNAVAILABLE` (serwis AI nie odpowiada), `502 UPSTREAM_ERROR` (Nominatim). Brak miejsca, punkt poza
Krakowem, punkt za daleko od drogi i brak ocen to **nie błędy**, tylko `intent: "clarify"` z komunikatem.

## Serwis AI (wewnętrzny, `X-Internal-Key`)

- `POST /assistant/plan` `{ query, language }` → `AssistantPlan` + `model`: `intent`, `restated`, `from_place`, `to_place`, `via_places` (do 3), `profile`, `weights`
  (`surface/views/safety/traffic`), `place_query`, `area`, `dimension`, `want` (best/worst), `count`.
- `POST /assistant/answer` `{ query, intent, facts[], language }` → `{ answer, model }`. `facts` to zdania zbudowane przez backend (do 40, do 700 znaków).
- `MOCK_AI=true`: prosty czytnik reguł (`assistant_mock.py`) rozumie „z A do B”, „rowerem/pieszo”, „ładne widoki/równa nawierzchnia/bezpiecznie/spokojnie”,
  „najładniejsze … na X”, „pokaż X”. Nie odmienia słów („z Rynku Głównego” zostaje odmienione), więc służy do demo i testów, nie do prawdziwej pracy.
- Prawdziwy model: `llm.py` (`plan`, `answer`), prompty po polsku, wynik jako obiekt Pydantic; w `answer` osobne wskazówki dla route / place / streets.

## Skąd fakty (backend)

| Fakt | Źródło |
|---|---|
| Trasa, czas, dystans, oceny wzdłuż trasy, pokrycie ocenami, porównanie z najszybszą | `graph_routes` (własny graf), te same dane co `POST /route` |
| Oceny ulic słowami (nawierzchnia „dobra”, ruch „spokojny”…) | widok `segment_scores`, średnia ważona długością |
| Ile jest ocen | tylko słowami („wielu użytkowników”, „bez własnych ocen: szacunek”) |
| Komentarze | 3 najnowsze widoczne komentarze na odcinkach trasy (oczyszczone z `<` `>`), tabela `comments` |
| Podsumowanie opinii | pole `overall` z `segment_summaries` |
| Przeszkody | aktywne wpisy z `obstacles` na odcinkach trasy |
| Ranking ulic | widok `fragment_map` (fragmenty 300–700 m), min. 2 oceny, a przy braku wyników 1 |
| Nazwy miejsc → współrzędne | Nominatim po stronie backendu (limit 1 zapytanie/s, własny User-Agent, cache 24 h; dla dzielnic także prawdziwy obrys) |

## Bezpieczeństwo i koszt

- Komentarze i opis użytkownika to **dane**: prompty każą ignorować zawarte w nich polecenia, a komentarze są oczyszczane z nawiasów kątowych,
  żeby nie zamknęły bloku `<facts>`.
- Model nie dostaje dostępu do bazy ani narzędzi; odpowiedź jest tylko tekstem. Wynik planu jest walidowany (Pydantic), a miejsca muszą leżeć w Krakowie.
- Limit 10/min na IP, krótkie zapytania (do 500 znaków); gdy model nie napisze odpowiedzi, użytkownik dostaje fakty (`model: "fallback"`).
- Za reverse proxy wszystkie żądania mają jeden adres IP: przed produkcją skonfigurować prawdziwy adres klienta (tak jak przy `POST /route`).

## Ograniczenia

- Nominatim zna miejsca i adresy z OpenStreetMap; nazwy potocznie odmienione model sprowadza do mianownika, ale mogą się zdarzyć błędy.
- „Moja lokalizacja” nie jest jeszcze obsługiwana: trzeba podać punkt początkowy.
- Opóźnienie ok. 5 s (miejsce, ulice) do 12 s (trasa): dwa wywołania modelu, geokodowanie i routing.
- Kontrakt (`docs/CONTRACT.md`) nie opisuje jeszcze `POST /assistant` ani `/assistant/*` serwisu AI: uzupełnia go osobny PR po akceptacji zespołu.

## Pliki

`ai-service/app/assistant_schemas.py`, `assistant_mock.py`, `llm.py`, `main.py` · `backend/app/assistant/`: `api.py` (endpoint i potok), `facts.py` (zdania z faktów),
`data.py` (SQL), `geocoding.py` (Nominatim), `river.py` (punkty przy rzece) · `frontend/src/components/assistant/AssistantPanel.tsx`, `App.tsx` (obsługa wyniku) ·
testy: `ai-service/tests/test_assistant.py`, `backend/tests/test_assistant.py`.
