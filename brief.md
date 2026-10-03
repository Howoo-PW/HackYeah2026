# Rate Your Ride — brief projektu

## Problem

Kierowcy, rowerzyści i motocykliści nie wiedzą, jak naprawdę wygląda droga, zanim nią pojadą. Nawigacje wybierają trasę wg czasu i dystansu, a pomijają to, co ważne w praktyce: stan nawierzchni, bezpieczeństwo, widoki, korki i dostępność parkingów. Informacje są rozproszone po forach i grupach w mediach społecznościowych, są nieaktualne i nie da się ich przeglądać na mapie. Zarządcy dróg nie mają taniego źródła danych o tym, gdzie jest najgorzej.

## Rozwiązanie

Mapowa aplikacja, w której użytkownicy oceniają **odcinki dróg** (nie całe drogi) w kilku wymiarach:

- jakość nawierzchni,
- widoki z trasy,
- bezpieczeństwo,
- obciążenie ruchem i problemy na drodze,
- dostępność parkingów,
- opcjonalne szczegóły drogi (np. rodzaj nawierzchni, szerokość, oświetlenie).

Kluczowe funkcje:

1. **Mapa kolorowana wg ocen** z filtrowaniem po wybranym wymiarze.
2. **Komentarze użytkowników** przy odcinkach.
3. **AI summary komentarzy**: krótkie podsumowanie opinii dla każdego odcinka, z oznaczeniem „wygenerowane przez AI" i dostępem do komentarzy źródłowych.
4. **Zgłaszanie przeszkód**, np. remontów i zamkniętych odcinków.

## Czemu takie rozwiązanie

- **Odcinki zamiast całych dróg**: jakość drogi zmienia się na długości, a ocena odcinka jest użyteczna.
- **Oddzielne wymiary zamiast jednej oceny**: różni użytkownicy chcą czegoś innego (widoki vs. szybkość vs. parking).
- **OpenStreetMap jako baza**: dane i mapa są darmowe, a licencja wymaga tylko atrybucji. Dzięki temu koszt startu jest bliski zera.
- **AI summary**: nikt nie czyta 50 komentarzy, a podsumowanie daje wartość nawet przy małej liczbie ocen.
- **Crowdsourcing**: tylko użytkownicy wiedzą, jak droga wygląda dziś. Żadna płatna usługa nie da takich danych o widokach czy parkingach.

**Główne ryzyka:** zimny start (pusta mapa), fałszywe oceny, nieaktualne dane i prywatność lokalizacji. Odpowiedź: start w jednym mieście, dane początkowe z OSM, logowanie, limity i wygasanie starych ocen.

## Finansowanie

Koszty utrzymania są niskie i zależą głównie od liczby użytkowników:

| Pozycja | Szacunek |
|---|---|
| Hosting bazy danych | darmowy plan na start, potem kilka–kilkadziesiąt USD/mies. |
| Domena | ok. 50–100 zł/rok |
| Mapa i dane (OSM) | 0 zł przy małym ruchu, potem hostowany dostawca kafelków |
| AI summary | grosze za odcinek przy małym modelu, wyniki cache'owane |

Źródła finansowania na później (do weryfikacji): granty i konkursy dla projektów smart city, współpraca z zarządcami dróg i miastami (raporty o stanie dróg), opcjonalna wersja premium (zaawansowane filtry, routing), partnerstwa z klubami rowerowymi i motocyklowymi.

## Przyszłość

- **Auto-routing** wg wybranych parametrów (np. „najlepsza nawierzchnia i widoki").
- Pasywne zbieranie danych z czujników telefonu (wykrywanie dziur).
- Aplikacja mobilna i tryb offline.
- Udostępnianie zagregowanych danych miastom i zarządcom dróg.
- Rozszerzenie na kolejne miasta i kraje.

## Plan implementacji

1. **Hackathon (MVP):** mapa OSM (Leaflet lub MapLibre) dla jednego miasta, podział dróg na odcinki, ocena 4–5 wymiarów, komentarze, kolorowanie z filtrem.
2. **Po MVP:** AI summary komentarzy (w tle, cache), logowanie i moderacja, zgłaszanie remontów i przeszkód.
3. **Kolejny etap:** wygasanie starych ocen, ocena wg pory dnia, ochrona przed nadużyciami.
4. **Później:** auto-routing, aplikacja mobilna, dane z czujników.

Dla demo na hackathonie: parking i ruch mogą być częściowo symulowane, ale trzeba to jasno zaznaczyć.
