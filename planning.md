# Plan for Izzy Uploader Service

## Cel projektu
Stworzenie prostego, łatwego w utrzymaniu serwisu, który importuje pojazdy z pliku CSV i synchronizuje je z platformą Izzylease, zapewniając możliwość rozwoju kolejnych logik biznesowych.

## Kontekst
- **Wejście**: plik CSV zawierający listę pojazdów wraz z ich specyfikacją (nagłówki dostępne w `_Planning/izzylease_lista_pol_import_pojazdow.csv`).
- **Wyjście**: rekordy pojazdów w systemie Izzylease zarządzane poprzez ich API (`_Planning/izzylease_external_api_docs_28112022.pdf`).

## Założenia architektoniczne
1. **Warstwa wejściowa** – moduł odpowiedzialny za wczytywanie i walidację pliku CSV.
2. **Warstwa domenowa** – obiekty reprezentujące pojazdy oraz logiki procesów synchronizacji.
3. **Warstwa integracji** – klient API Izzylease obsługujący operacje CRUD oraz dodatkowe działania (zamknięcie oferty, aktualizacja ceny itp.).
4. **Warstwa orkiestracji procesów** – konfigurowalne „pipeline’y” pozwalające uruchamiać różne scenariusze (prosty import, zamykanie brakujących pojazdów, aktualizacja cen).
5. **Warstwa prezentacji** (opcjonalna) – proste CLI / endpoint HTTP do uruchamiania procesów i podglądu wyników.

## Harmonogram prac

### Faza 1 – Podstawy projektu
- Skonfigurowanie repozytorium (struktura katalogów: `src/`, `tests/`, `config/`, `scripts/`).
- Przygotowanie środowiska uruchomieniowego (Python + poetry/pipenv + konfiguracja `.env`).
- Utworzenie klasy `Vehicle` i walidacji danych wejściowych (np. `pydantic`).
- Implementacja parsera CSV zwracającego listę obiektów domenowych wraz z raportem błędów.

### Faza 2 – Integracja z API Izzylease
- Analiza dokumentacji API w `_Planning/izzylease_external_api_docs_28112022.pdf`.
- Stworzenie modułu `izzylease_client` z obsługą autoryzacji, logowania błędów i ponowień.
- Zaimplementowanie metod: `create_vehicle`, `close_vehicle`, `update_vehicle`, `update_price` (nazwy robocze).
- Przygotowanie testów jednostkowych z wykorzystaniem `responses`/`requests-mock` do symulacji API.

### Faza 3 – Scenariusze procesów
1. **Prosty import**
   - Orkiestrator `import_pipeline` wykonujący: wczytanie CSV → walidacja → tworzenie pojazdów (równoległe/kolejkowane).
   - Raport końcowy z liczbą sukcesów, błędów i szczegółami.
2. **Zamykanie brakujących pojazdów**
   - Pobranie listy aktywnych pojazdów z Izzylease.
   - Porównanie z listą z CSV (np. po `external_id`).
   - Wywołanie `close_vehicle` dla brakujących rekordów.
3. **Aktualizacja cen**
   - Porównanie cen z CSV i API.
   - Jeśli cena spadła → wywołanie `update_price` z flagą obniżki.
   - W innych przypadkach aktualizacja standardowa (jeżeli API wymaga).

### Faza 4 – Logowanie, monitoring, retry
- Centralny logger z korelacją rekordów pojazdów.
- Mechanizmy ponowień przy błędach komunikacji.
- Obsługa limitów API (throttling, backoff).

### Faza 5 – Interfejs użytkownika
- CLI (np. `click`) umożliwiające wybór scenariusza i ścieżki pliku CSV.
- Opcjonalnie prosty serwis HTTP (FastAPI/Flask) z endpointem przesyłającym plik CSV.
- Dokumentacja użytkownika (README, przykładowe komendy, opis pliku konfiguracyjnego).

### Faza 6 – Automatyzacja i DevOps
- Konfiguracja CI (lint + testy).
- Szablon `.env.example` z wymaganymi zmiennymi (API key, base URL).
- Dockerfile i docker-compose do lokalnego uruchamiania.

## Plan testów
- Testy jednostkowe parsera CSV (poprawne wczytanie, błędne dane, brak wymaganych pól).
- Testy integracyjne klienta API z mockiem.
- Testy scenariuszy pipeline’ów (mock API, sprawdzenie decyzji import/zamknięcie/aktualizacja ceny).
- Testy e2e (CLI/HTTP) z użyciem próbnego pliku CSV.

## Roadmapa rozszerzeń
- Wsparcie dla wielu plików (batche, harmonogram crona).
- Integracja z systemem kolejkowym (RQ/Celery) dla dużych wolumenów.
- Dashboard z raportami (np. Grafana + Prometheus, ewentualnie integracja z BI).
- Mechanizm weryfikacji zdjęć oraz metadanych pojazdów.

## Ryzyka i środki zaradcze
- **Zmiana API Izzylease** – utrzymywać warstwę klienta odseparowaną, testy kontraktowe.
- **Błędy danych w CSV** – walidacja, raporty błędów i możliwość ponownego importu.
- **Limity API** – backoff, kolejkowanie, konfiguracja limitów równoległych zapytań.
- **Bezpieczeństwo** – bezpieczne przechowywanie kluczy (vault, secret manager), logowanie bez danych wrażliwych.

## Następne kroki
1. Przygotować minimalny szkielet aplikacji wraz z parserem CSV. ✅ Wdrożono w `src/izzy_uploader/` (moduły `models.py`, `csv_loader.py`).
2. Zaimplementować klienta API i scenariusz „prosty import”. ✅ Dostępne w `client.py` i `pipelines/import_pipeline.py`.
3. Rozszerzyć o scenariusze zamykania brakujących ofert i aktualizacji cen. ✅ Obsługiwane przez `VehicleSynchronizer` (parametry `close_missing`, `update_prices`).
4. Dodać interfejs użytkownika i automatyzację. ✅ CLI `izzy-uploader` w `cli.py`; automatyzacja testów przez `pytest`.
5. Utrzymywać dokumentację i testy wraz z rozwojem. ✅ Dodano testy jednostkowe i zaktualizowano `READ.md`.
