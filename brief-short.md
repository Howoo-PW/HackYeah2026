# Rate Your Ride — oceń drogi jak restauracje

## Problem
Nawigacja wybiera trasę według czasu, a nie jakości. Prowadzi pod adres, gdzie nie ma gdzie zaparkować, przez nierówną nawierzchnię i progi, na które nie jest gotowe niskie auto, albo przez nudną trasę, kiedy motocyklista chce ładnej. Pokazuje bieżące zdarzenia, ale nie to, gdzie jest niebezpiecznie na co dzień. Ładnej drogi nie da się polecić innym.

## Rozwiązanie
Mapa dróg (pilotaż w Krakowie, docelowo cała Europa), na której użytkownicy oceniają odcinki dróg (nawierzchnia, widoki, bezpieczeństwo, ruch, parkingi) i piszą opinie. Mapa jest kolorowana wg ocen, a AI streszcza komentarze. Trasę można wyznaczyć w trybie „unikaj złych dróg” albo „wybierz ładną”.

## Czemu takie
- **Odcinki, nie całe drogi:** jakość zmienia się na długości.
- **Osobne wymiary:** każdy szuka czego innego (widoki, gładka nawierzchnia, parking).
- **Społeczność (community contribution) i OpenStreetMap:** oceny, zdjęcia i zgłoszenia dodają użytkownicy, a takich danych nie ma w płatnych usługach. Mapa jest darmowa, a każde nowe miasto zaczyna się od lokalnej społeczności.

## Finansowanie
Start prawie za darmo: darmowe plany bazy, mapy i tras, domena ok. 50–100 zł/rok. Dalej granty smart city, dane i raporty dla miast, wersja premium.

## Przyszłość
Własny routing po ocenach, statystyki wypadków, wykrywanie dziur czujnikami telefonu, aplikacja mobilna, a po pilotażu w Krakowie kolejne miasta i cała Europa.

## Plan implementacji
1. **Hackathon:** mapa z ocenami i komentarzami, AI summary, trasy wg ocen (część danych przykładowa).
2. **Potem:** moderacja, zdjęcia, zgłaszanie remontów.
3. **Później:** własny routing, aplikacja mobilna.
