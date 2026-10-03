# Rate Your Ride — kontrakt wspólny

Ten plik jest **jedynym źródłem prawdy** dla wszystkiego, co łączy frontend, backend, bazę i serwis AI: endpointów, formatów danych, nazw, enumów, portów i zmiennych środowiskowych.

Zatwierdzamy go **przed** utworzeniem gałęzi. Potem każdy pracuje niezależnie, a frontend używa przykładów z tego pliku jako mocków.

Powiązane: [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md).

---

## 1. Zatwierdzenie

| Osoba | Obszar | Zatwierdzone |
|---|---|---|
| FE | frontend | ☑ 2026-10-03 |
| B1 | backend + infrastruktura | ☑ 2026-10-03 |
| B2 | backend + baza danych | ☑ 2026-10-03 |
| AI | serwis AI + backend | ☑ 2026-10-03 |

**Zmiana kontraktu po starcie:** osobny PR tylko z tym plikiem, akceptacja wszystkich osób, których dotyczy zmiana. Nie zmieniamy kontraktu „przy okazji” w PR-ze z kodem.

---

## 2. Konwencje ogólne

| Temat | Ustalenie |
|---|---|
| Bazowy URL backendu | `http://localhost:8000/api/v1` (lokalnie) |
| Wersjonowanie | Prefiks `/api/v1`. Zmiany łamiące = nowa wersja |
| Format | JSON, UTF-8. Wyjątek: przesyłanie zdjęć (`multipart/form-data`) |
| Nazwy pól | `snake_case` w JSON, bazie i Pythonie. Frontend nie konwertuje nazw |
| Daty | ISO 8601 w UTC, np. `2026-10-03T14:20:00Z` |
| Identyfikatory | Odcinki i parkingi: `integer`. Użytkownicy: `uuid` (z Supabase Auth). Oceny, komentarze, przeszkody, zdjęcia: `uuid` |
| Współrzędne | **GeoJSON: `[lon, lat]`** (najpierw długość!). W polach obiektowych: `{ "lat": 50.06, "lon": 19.94 }` |
| `bbox` | `minLon,minLat,maxLon,maxLat`. Kraków: `19.792,49.967,20.217,50.126` |
| Poza Krakowem | Współrzędne spoza bbox Krakowa → `422 OUT_OF_AREA` |
| Paginacja | Parametry `page` (od 1) i `page_size` (domyślnie 20, max 100). Odpowiedź: `{ "items": [...], "page", "page_size", "total" }` |
| Uwierzytelnianie | Nagłówek `Authorization: Bearer <JWT z Supabase>` |
| Puste wartości | Brak danych = `null`, nie pomijamy pola |

### Format błędu (wszystkie usługi)

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Pole 'surface' musi być w zakresie 1–5",
    "details": { "field": "surface" }
  }
}
```

| HTTP | `code` | Kiedy |
|---|---|---|
| 400 | `BAD_REQUEST` | Niepoprawne żądanie |
| 401 | `UNAUTHORIZED` | Brak lub nieważny token |
| 403 | `FORBIDDEN` | Brak uprawnień (np. nie admin) |
| 404 | `NOT_FOUND` | Brak zasobu |
| 413 | `FILE_TOO_LARGE` | Zdjęcie > 5 MB |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Zły typ pliku |
| 422 | `VALIDATION_ERROR` | Błąd walidacji pól |
| 422 | `OUT_OF_AREA` | Współrzędne poza Krakowem |
| 429 | `RATE_LIMITED` | Za dużo żądań |
| 502 | `UPSTREAM_ERROR` | Błąd serwisu AI lub silnika tras |
| 500 | `INTERNAL_ERROR` | Inny błąd serwera |

---

## 3. Enumy i słowniki

Te same wartości w bazie (typy `enum` lub `check`), backendzie (Pydantic) i frontendzie (TypeScript).

| Enum | Wartości |
|---|---|
| `Dimension` | `surface`, `views`, `safety`, `traffic`, `parking` |
| `TimeOfDay` | `morning` (6–10), `day` (10–16), `evening` (16–22), `night` (22–6) |
| `ObstacleType` | `roadwork`, `closure`, `pothole`, `accident`, `other` |
| `ContentStatus` | `visible`, `hidden` |
| `Role` | `user`, `admin` |
| `Confidence` | `low`, `medium`, `high` |

### Znaczenie ocen (skala 1–5, wszędzie **5 = najlepiej**)

| Wymiar | Nazwa w UI | 1 | 5 |
|---|---|---|---|
| `surface` | Nawierzchnia | dziury, zniszczona | gładka, nowa |
| `views` | Widoki | brzydko, nic ciekawego | piękne widoki |
| `safety` | Bezpieczeństwo | niebezpiecznie | bezpiecznie |
| `traffic` | Obciążenie / problemy | ciągłe korki, problemy | płynnie, bez problemów |
| `parking` | Parkingi | brak miejsc | łatwo zaparkować |

Uwaga: przy `traffic` wyższa ocena oznacza **mniejszy** ruch. Nie odwracamy skali nigdzie w kodzie.

---

## 4. Typy danych

Zapis w stylu TypeScript. Backend odwzorowuje je w Pydantic, frontend w `frontend/src/api/types.ts`.

```ts
type Scores = {
  surface: number | null;   // średnia 1.0–5.0, null = brak ocen
  views: number | null;
  safety: number | null;
  traffic: number | null;
  parking: number | null;
};

type SegmentProperties = {
  id: number;
  osm_way_id: number;
  name: string | null;
  highway: string;            // tag OSM, np. "primary", "residential"
  length_m: number;
  scores: Scores;             // efektywne: własne oceny, a bez nich szacunek z grupy (patrz niżej)
  scores_own: Scores;         // zwykłe średnie z ocen samego odcinka (null = brak)
  scores_source: "own" | "group" | "none";   // skąd wynik: własne oceny / sąsiednie odcinki grupy / brak
  confidence: "none" | "low" | "medium" | "high";
  group: GroupRef | null;     // odcinek ulicy, do którego należy ten kawałek
  ratings_count: number;      // tylko własne oceny odcinka
  active_obstacles_count: number;
};

type GroupRef = {             // grupa = kolejne kawałki jednej ulicy, ok. 500 m
  id: number;
  name: string | null;
  highway: string;
  length_m: number;
  segments_count: number;
  from_street: string | null; // najważniejsza inna ulica na początku grupy
  to_street: string | null;   // ... i na końcu
  ratings_count: number;      // oceny wszystkich odcinków grupy
};

type GroupDetail = GroupRef & {
  scores: Scores;             // średnie grupy (ściągane do średniej typu drogi, gdy ocen jest mało)
  geometry: GeoJSON.MultiLineString;
  segment_ids: number[];
};

type SegmentDetail = SegmentProperties & {
  geometry: GeoJSON.LineString;
  surface_osm: string | null;     // np. "asphalt"
  smoothness_osm: string | null;
  maxspeed: number | null;
  lit: boolean | null;
  last_rating_at: string | null;
  scores_by_time_of_day: Record<TimeOfDay, Scores>;
  summary: Summary | null;        // null = za mało komentarzy
  obstacles: Obstacle[];
  photos_count: number;
  my_rating: Rating | null;       // tylko dla zalogowanego
};

type Rating = {
  id: string;
  segment_id: number;
  surface: number | null;   // 1–5 (całkowite)
  views: number | null;
  safety: number | null;
  traffic: number | null;
  parking: number | null;
  time_of_day: TimeOfDay;
  created_at: string;
};

type Comment = {
  id: string;
  segment_id: number;
  author: { id: string; display_name: string };
  text: string;               // 1–1000 znaków
  status: ContentStatus;      // użytkownicy widzą tylko "visible"
  created_at: string;
};

type Obstacle = {
  id: string;
  segment_id: number | null;
  type: ObstacleType;
  description: string | null; // ≤ 500 znaków
  location: { lat: number; lon: number };
  valid_until: string | null; // null = do odwołania
  reported_by: string;        // uuid
  created_at: string;
};

type ParkingSpot = {
  id: number;
  osm_id: number;
  name: string | null;
  capacity: number | null;
  fee: boolean | null;
  location: { lat: number; lon: number };
};

type Photo = {
  id: string;
  segment_id: number;
  url: string;                // podpisany URL, ważny 1 h
  thumbnail_url: string;
  taken_at: string | null;
  created_at: string;
};

type Summary = {
  surface: string;            // "brak informacji", jeśli nikt nie pisał
  views: string;
  safety: string;
  traffic: string;
  parking: string;
  overall: string;            // 1 zdanie
  confidence: Confidence;
  conflicts: string[];        // rozbieżne opinie
  comments_count: number;
  model: string;
  updated_at: string;
};

type Profile = {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  created_at: string;
};
```

---

## 5. API backendu

Dostęp: **P** = publiczny, **U** = zalogowany użytkownik, **A** = admin.

### 5.1 System

#### `GET /health` — P

```json
{ "status": "ok", "version": "0.1.0", "checks": { "database": "ok", "ai_service": "ok", "routing": "ok" } }
```

`status`: `ok` / `degraded` (coś poza bazą nie działa) / `down` (baza nie działa, HTTP 503).

#### `GET /me` — U

Odpowiedź: `Profile`.

### 5.2 Odcinki

#### `GET /segments` — P

| Parametr | Wymagany | Opis |
|---|---|---|
| `bbox` | tak | Obszar mapy |
| `dimension` | nie | `Dimension` — dla filtra |
| `min_score` | nie | 1–5, tylko odcinki z oceną ≥ (wymaga `dimension`) |
| `rated_only` | nie | `true` = tylko odcinki z ocenami |

Limit: max 2000 odcinków na odpowiedź. Przy większym obszarze → `422 VALIDATION_ERROR` („przybliż mapę”).

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "LineString", "coordinates": [[19.9370, 50.0614], [19.9385, 50.0621]] },
      "properties": {
        "id": 1042,
        "osm_way_id": 23456789,
        "name": "ulica Grodzka",
        "highway": "residential",
        "length_m": 142.5,
        "scores": { "surface": 3.8, "views": 4.9, "safety": 4.1, "traffic": 2.2, "parking": 1.4 },
        "ratings_count": 27,
        "active_obstacles_count": 0
      }
    }
  ]
}
```

**Grupy i wynik efektywny.** OSM tnie drogi na każdym skrzyżowaniu, więc połowa odcinków ma
poniżej 100 m i nikt ich nie oceni. Odcinki (`id`) i oceny zostają bez zmian. Dodatkowo kolejne
kawałki jednej ulicy (ta sama nazwa i typ drogi) tworzą **grupę** po ok. 500 m. Wynik `scores`
odcinka liczy się tak: własne oceny odcinka (ważą tyle, co 2 oceny grupy), w przeciwnym razie
średnia pozostałych odcinków grupy, ściągana do średniej typu drogi, gdy ocen jest mało.
`scores_source` mówi, skąd wynik: `own`, `group` (szacunek, pokaż jaśniej) lub `none`.
`rated_only` i `min_score` działają na wyniku efektywnym i filtrują po limicie 2000 odcinków.

#### `GET /groups/{id}` — P

Odpowiedź: `GroupDetail`: scalona geometria do podświetlenia na mapie, id odcinków i średnie
grupy. Nieznane id → `404 NOT_FOUND`.

#### `GET /segments/nearest?lat=&lon=` — P

Najbliższy odcinek w promieniu 50 m. Odpowiedź: `SegmentProperties` + `distance_m`. Brak odcinka → `404`.

#### `GET /segments/{id}` — P (pole `my_rating` tylko dla U)

Odpowiedź: `SegmentDetail`.

### 5.3 Oceny

#### `POST /segments/{id}/ratings` — U

```json
{ "surface": 4, "views": 5, "safety": null, "traffic": 2, "parking": null, "time_of_day": "evening" }
```

- Co najmniej jeden wymiar różny od `null`.
- `time_of_day` opcjonalne. Brak → backend ustala z czasu serwera (strefa `Europe/Warsaw`).
- Druga ocena tego samego odcinka tego samego dnia **zastępuje** pierwszą.

Odpowiedź: `201` (nowa) lub `200` (zastąpiona), treść: `Rating`.

### 5.4 Komentarze

#### `GET /segments/{id}/comments?page=&page_size=` — P

Odpowiedź: paginowana lista `Comment`, najnowsze pierwsze.

#### `POST /segments/{id}/comments` — U

```json
{ "text": "Nowy asfalt od mostu, ale wieczorem korki." }
```

Odpowiedź: `201`, `Comment`.

### 5.5 Przeszkody

#### `GET /obstacles?bbox=` — P

Tylko aktywne (`valid_until` w przyszłości lub `null`). Odpowiedź: `{ "items": Obstacle[] }`.

#### `POST /obstacles` — U

```json
{ "type": "roadwork", "description": "Remont nawierzchni, ruch wahadłowy", "location": { "lat": 50.0547, "lon": 19.9356 }, "valid_until": "2026-10-20T00:00:00Z" }
```

Backend sam przypisuje `segment_id` (najbliższy odcinek w promieniu 50 m). Odpowiedź: `201`, `Obstacle`.

### 5.6 Parkingi

#### `GET /parking?bbox=` — P

Odpowiedź: `{ "items": ParkingSpot[] }`.

### 5.7 Zdjęcia

#### `GET /segments/{id}/photos?page=&page_size=` — P

Odpowiedź: paginowana lista `Photo`.

#### `POST /segments/{id}/photos` — U

`multipart/form-data`: pole `file` (JPEG / PNG / WebP, ≤ 5 MB), opcjonalnie `taken_at`. Backend usuwa EXIF i tworzy miniaturę.

Odpowiedź: `201`, `Photo`.

### 5.8 Trasy

#### `POST /route` — P

```json
{
  "from": { "lat": 50.0614, "lon": 19.9370 },
  "to": { "lat": 50.0470, "lon": 19.9440 },
  "profile": "driving-car",
  "weights": { "surface": 2, "views": 1, "safety": 1, "traffic": 0, "parking": 0 }
}
```

- `profile`: `driving-car` / `cycling-regular` / `foot-walking`.
- `weights`: 0–3 dla każdego wymiaru, brakujący = 0. Wszystkie 0 → sortowanie po czasie przejazdu.

```json
{
  "routes": [
    {
      "rank": 1,
      "geometry": { "type": "LineString", "coordinates": [[19.9370, 50.0614], [19.9440, 50.0470]] },
      "distance_m": 2140,
      "duration_s": 420,
      "score": 4.1,
      "scores": { "surface": 4.3, "views": 4.6, "safety": 3.9, "traffic": 2.8, "parking": null },
      "coverage": 0.62,
      "segment_ids": [1042, 1043, 1107]
    }
  ]
}
```

`coverage` = część długości trasy (0–1), która ma oceny. Frontend pokazuje ją użytkownikowi.

### 5.9 Administracja

| Endpoint | Treść | Odpowiedź |
|---|---|---|
| `PATCH /admin/comments/{id}` — A | `{ "status": "hidden" }` | `Comment` |
| `PATCH /admin/photos/{id}` — A | `{ "status": "hidden" }` | `Photo` |
| `DELETE /admin/obstacles/{id}` — A | — | `204` |
| `POST /admin/summaries/{segment_id}/refresh` — A | — | `Summary` |

---

## 6. API serwisu AI (wewnętrzne)

- Adres w Compose: `http://ai:8000`. Lokalnie: `http://localhost:8001`.
- Każde żądanie (poza `/health`) wymaga nagłówka `X-Internal-Key: <INTERNAL_API_KEY>`. Brak → `401`.
- Backend ustawia timeout 15 s. Przy błędzie lub timeoucie pokazuje komentarze bez podsumowania.
- Tryb `MOCK_AI=true` zwraca stałe odpowiedzi takie jak przykłady poniżej.

#### `GET /health`

```json
{ "status": "ok", "provider": "google_genai", "model": "gemini-2.5-flash", "mock": false }
```

#### `POST /summarize`

```json
{
  "segment_id": 1042,
  "language": "pl",
  "comments": [
    { "id": "6f1c…", "text": "Piękny widok na Wawel, ale dziury przy skrzyżowaniu.", "created_at": "2026-09-28T17:10:00Z" }
  ]
}
```

- Max 50 komentarzy (backend wysyła najnowsze).
- Min 5 komentarzy — przy mniejszej liczbie backend nie wywołuje AI.

Odpowiedź: `Summary` bez pól `updated_at` (ustawia backend).

#### `POST /analyze-surface` (opcjonalnie)

```json
{ "segment_id": 1042, "image_urls": ["https://…/photo1.jpg"] }
```

```json
{ "surface": "asphalt", "condition": 3, "potholes": true, "cracks": false, "confidence": "medium" }
```

---

## 7. Baza danych — nazwy wspólne

Pełny schemat w [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md#3-struktura-danych-supabase). Tu tylko to, czego używają inne obszary:

| Element | Nazwa |
|---|---|
| Tabele | `profiles`, `segments`, `segment_groups`, `ratings`, `comments`, `obstacles`, `parking_spots`, `segment_photos`, `segment_summaries` |
| Widok materializowany | `segment_stats` |
| Bucket Storage | `segment-photos` (prywatny) |
| Rola admina | `auth.users.raw_app_meta_data ->> 'role' = 'admin'` |
| SRID | `4326` |

---

## 8. Porty, usługi i zmienne

| Usługa (Compose) | Port lokalny | Port w kontenerze |
|---|---|---|
| `frontend` | 5173 | 5173 |
| `backend` | 8000 | 8000 |
| `ai` | 8001 | 8000 |

Nazwy zmiennych środowiskowych — lista w [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md#5-bezpieczeństwo) (sekcja „Zmienne `.env`”) i w `.env.example`. Nowa zmienna = aktualizacja `.env.example` w tym samym PR.

---

## 9. Limity

| Akcja | Limit na użytkownika |
|---|---|
| Oceny | 30 / h |
| Komentarze | 10 / h |
| Przeszkody | 10 / h |
| Zdjęcia | 20 / h |
| `POST /route` | 30 / min na IP |

---

## 10. Do ustalenia na spotkaniu

- [x] Skala i znaczenie wymiarów (sekcja 3)
- [x] Typy danych (sekcja 4)
- [x] Endpointy i przykłady (sekcja 5)
- [x] Kontrakt AI (sekcja 6)
- [x] Nazwy tabel i bucketu (sekcja 7)
- [x] Porty i zmienne (sekcja 8)
- [x] Limity (sekcja 9)
