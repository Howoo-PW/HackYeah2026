# Rate Your Ride — brief projektu

**Oceń drogi jak restauracje.**

## Problem

Chyba każdy kierowca został kiedyś przez nawigację wyprowadzony na tak zwane „manowce”. Nawigacja wybiera trasę według czasu i dystansu, a to, co decyduje o jakości przejazdu, zostaje poza mapą:

- **Parkowanie.** Nawigacja doprowadzi pod wskazany adres, ale okazuje się, że w promieniu kilku przecznic wszystkie miejsca są zajęte.
- **Stan drogi.** Właściciel auta z niskim zawieszeniem musi zawracać przed nierówną nawierzchnią i zbyt wysokimi progami zwalniającymi.
- **Bezpieczeństwo.** Nawigacja pokazuje aktualne zdarzenia, ale nie statystyki: nie wiadomo, gdzie wypadki zdarzają się codziennie.
- **Przyjemność jazdy.** Motocyklista planuje przejażdżkę, a wybrana trasa jest nużąca. Nie ma sposobu, żeby poprosić o ładniejszą.
- **Brak polecania.** Przejechałeś piękną drogę i chcesz ją polecić innym, ale zwykła nawigacja tego nie umożliwia.

Wiedza o drogach istnieje, ale jest rozproszona po forach i grupach w mediach społecznościowych, szybko się starzeje i nie da się jej oglądać na mapie. Zarządcy dróg nie mają taniego źródła informacji o tym, gdzie jest najgorzej.

## Rozwiązanie

Mapowa aplikacja, w której użytkownicy oceniają **odcinki dróg** i opisują je komentarzem, tak jak restauracje w serwisach z opiniami. Oceny są w kilku wymiarach (skala 1–5):

- jakość nawierzchni,
- widoki z trasy,
- bezpieczeństwo,
- obciążenie ruchem i problemy na drodze,
- dostępność parkingów,
- opcjonalne szczegóły drogi (np. progi zwalniające, rodzaj nawierzchni, oświetlenie).

Kluczowe funkcje:

1. **Mapa kolorowana wg ocen** z filtrem wymiaru: od razu widać, które drogi są dobre, a które złe.
2. **Oceny i opinie użytkowników** przy odcinkach, ze zdjęciami.
3. **AI summary komentarzy**: krótkie podsumowanie opinii o odcinku, oznaczone jako wygenerowane przez AI, z dostępem do komentarzy źródłowych.
4. **Zgłaszanie przeszkód**: remonty, zamknięcia, uszkodzenia.
5. **Wyznaczanie trasy według ocen**: tryb „unikaj złych dróg” i tryb „wybierz ładną trasę”, z wagami wymiarów ustawianymi przez użytkownika.
6. **Polecanie dróg**: ładny odcinek można ocenić i polecić innym.

## Czemu takie rozwiązanie

- **Odcinki zamiast całych dróg**: jakość zmienia się na długości drogi, a ocena odcinka jest użyteczna.
- **Oddzielne wymiary zamiast jednej oceny**: kierowca niskiego auta, motocyklista i osoba szukająca parkingu chcą czegoś innego.
- **Crowdsourcing**: tylko użytkownicy wiedzą, jak droga wygląda dziś. Żadna płatna usługa nie da takich danych o widokach czy parkingach.
- **Znany schemat**: oceny i opinie jak przy restauracjach nie wymagają tłumaczenia.
- **OpenStreetMap jako baza**: dane i mapa są darmowe, a licencja wymaga tylko atrybucji. Koszt startu jest bliski zera.
- **AI summary**: nikt nie czyta 50 komentarzy, a podsumowanie daje wartość nawet przy małej liczbie ocen.

**Główne ryzyka i odpowiedzi:**

| Ryzyko | Odpowiedź |
|---|---|
| Zimny start: pusta mapa | Start w jednym mieście (Kraków), dane początkowe z OSM, kilkadziesiąt ocen dla demo |
| Fałszywe oceny | Logowanie, limity, moderacja |
| Nieaktualne dane | Wygasanie starych ocen, daty przy ocenach |
| Prywatność lokalizacji | Zbieramy oceny odcinków, nie ślady przejazdów |
| Limity darmowych usług map | Cache tras i zapytań, w razie potrzeby własny routing |

## Finansowanie

Koszty utrzymania są niskie i zależą głównie od liczby użytkowników:

| Pozycja | Szacunek |
|---|---|
| Hosting bazy danych | darmowy plan na start, potem kilka–kilkadziesiąt USD/mies. |
| Domena | ok. 50–100 zł/rok |
| Mapa i dane (OSM) | 0 zł przy małym ruchu, potem hostowany dostawca kafelków |
| Trasy | darmowy plan dostawcy na start (ma dzienny limit), potem własny serwer tras |
| AI summary | niski koszt za odcinek przy małym modelu, wyniki cache'owane |

Źródła finansowania na później (do weryfikacji): granty i konkursy dla projektów smart city, współpraca z zarządcami dróg i miastami (raporty o stanie dróg i statystyki), wersja premium (zaawansowane filtry, wyznaczanie tras), partnerstwa z klubami rowerowymi i motocyklowymi.

## Przyszłość

- **Trasy optymalizowane po ocenach** na własnym grafie dróg (zamiast wybierania spośród kilku tras z zewnętrznego serwisu).
- **Statystyki bezpieczeństwa**: miejsca zdarzeń drogowych z danych publicznych obok ocen użytkowników.
- Pasywne zbieranie danych z czujników telefonu (wykrywanie dziur i progów).
- Aplikacja mobilna i tryb offline.
- Udostępnianie zagregowanych danych miastom i zarządcom dróg.
- **Skalowanie z pilotażu na całą Europę:** Kraków to pilotaż, docelowo kolejne miasta i kraje (dane OpenStreetMap obejmują cały kontynent).

## Plan implementacji

1. **Hackathon (MVP):** mapa OSM dla Krakowa, odcinki dróg, oceny i komentarze, kolorowanie z filtrem, podsumowania AI komentarzy, wyznaczanie tras z uwzględnieniem ocen.
2. **Po MVP:** moderacja, zdjęcia, zgłaszanie przeszkód, wygasanie starych ocen, ocena wg pory dnia.
3. **Później:** własny routing, aplikacja mobilna, dane z czujników, rozszerzenie z Krakowa na kolejne miasta i całą Europę.

Dla demo na hackathonie: część danych (parking, ruch, oceny odcinków) może pochodzić z przykładowego zestawu, ale trzeba to jasno zaznaczyć.
