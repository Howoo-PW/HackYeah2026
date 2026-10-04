# Rate My Road — scenariusz oceny

Otwórz http://localhost:5173 po uruchomieniu zgodnie z [JURY.md](../JURY.md).
Testy mapy, tras i asystenta można wykonywać bez logowania. Do zapisania
własnych ocen, opinii i zdjęć potrzebne jest zwykłe konto użytkownika.

| Test | Działanie | Oczekiwany wynik |
|---|---|---|
| Mapa i oceny | Przybliż mapę Krakowa, kliknij ulicę lub odcinek. | Panel pokazuje oceny wymiarów, informacje o drodze, dostępne opinie i zdjęcia. Kolory dróg obrazują wybrany wymiar oceny. |
| Filtry | Zmień wymiar oceny i minimalną ocenę. | Mapa prezentuje odcinki zgodnie z wybranym kryterium. |
| Trasy | Wybierz dwa punkty w Krakowie i wyznacz trasę. Powtórz dla samochodu, roweru i pieszego. | Trasa pojawia się na mapie z dystansem i czasem, zgodnie z wybranym środkiem transportu. |
| Preferencje tras | Zwiększ wagę nawierzchni, widoków lub bezpieczeństwa i przelicz trasę. | Trasy uwzględniają wybrane priorytety; wariant może się zmienić, jeśli graf oferuje alternatywę. |
| Asystent AI | Wpisz „rowerem z Rynku Głównego na Wawel, ładne widoki”. | Asystent interpretuje zapytanie, wyznacza trasę rowerową i opisuje ją na podstawie danych aplikacji. |
| Asystent nad Wisłą | Wpisz „pieszo z Wawelu na Kazimierz wzdłuż Wisły”. | Asystent próbuje uwzględnić przebieg wzdłuż rzeki w dostępnej sieci tras. |
| Konto użytkownika | Zarejestruj konto z własnym adresem e-mail. Jeśli wymaga tego konfiguracja Auth, potwierdź e-mail i zaloguj się ponownie w aplikacji. | Aplikacja pokazuje zalogowanego użytkownika i udostępnia zapis własnych treści. |
| Ocena i opinia | Na wybranym odcinku ustaw oceny, wpisz krótką opinię i zapisz. | Ocena i opinia zostają zapisane i są widoczne po ponownym otwarciu odcinka lub odświeżeniu strony. |
| Zdjęcia | Przy wystawianiu oceny dołącz zdjęcie drogi w JPEG, PNG lub WebP, do 5 MB. | Zdjęcie zostaje zapisane i jest dostępne w panelu odcinka. |
| Podsumowanie AI | Wybierz odcinek z opiniami lub zdjęciami i odczytaj podsumowanie. | Podsumowanie odnosi się do dostępnych treści. Jeśli trwa generowanie, pojawia się informacja o przygotowywaniu. Przy niewystarczających danych aplikacja informuje o ich braku. |

Prototyp obejmuje Kraków. Punkty spoza obszaru i miejsca zbyt odległe od sieci
dróg mogą zostać odrzucone z komunikatem. Dane ocen zależą od dostępnych
ocen użytkowników i danych demonstracyjnych; nie wszystkie drogi mają opinie.
Odpowiedzi AI, kafelki mapy i logowanie wymagają internetu.

Wszystkie zapisy trafiają do współdzielonej bazy demonstracyjnej zespołu.
Do testów używaj treści i zdjęć dotyczących dróg.
