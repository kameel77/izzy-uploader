# Izzy Uploader

Mini serwis do synchronizacji pojazdów z platformą Izzylease na podstawie plików CSV.

Repozytorium zawiera w pełni działający szkielet aplikacji w Pythonie obejmujący parser CSV,
klienta HTTP oraz orkiestrator procesów z wierszem poleceń.

## Założenia
- Źródłem danych jest plik CSV z nagłówkami zgodnymi z `_Planning/izzylease_lista_pol_import_pojazdow.csv`.
- Serwis komunikuje się z API Izzylease (szczegóły w `_Planning/izzylease_external_api_docs_28112022.pdf`).
- Projekt ma pozostać prosty, rozszerzalny i łatwy w utrzymaniu.

## Kluczowe scenariusze
1. **Import pojazdów** – tworzenie rekordów w Izzylease na podstawie danych z CSV.
2. **Zamykanie ofert** – wykrywanie pojazdów brakujących w CSV i zamykanie ich poprzez API.
3. **Aktualizacja cen** – porównywanie cen i aktualizacja rekordów, w tym zgłaszanie obniżek.

## Struktura katalogów
```
/READ.md              – szybkie wprowadzenie do repozytorium
/planning.md          – szczegółowy plan prac i roadmapa
/pyproject.toml       – konfiguracja projektu Python
/src/izzy_uploader/   – kod źródłowy aplikacji
  cli.py              – interfejs CLI `izzy-uploader`
  client.py           – klient HTTP Izzylease
  config.py           – obsługa konfiguracji środowiskowej
  csv_loader.py       – parser CSV do obiektów domenowych
  models.py           – definicje modeli domenowych
  pipelines/          – scenariusze synchronizacji (import, zamknięcia, ceny)
/tests/               – testy jednostkowe (pytest)
/_Planning/           – materiały referencyjne (CSV, dokumentacja API)
```

## Uruchomienie CLI
1. Zainstaluj zależności projektu (np. `pip install -e .[dev]`).
2. Ustaw zmienne środowiskowe:
   - `IZZYLEASE_API_BASE_URL` – adres API (np. `https://api.izzylease.pl`)
   - `IZZYLEASE_CLIENT_ID` oraz `IZZYLEASE_CLIENT_SECRET` – dane do autoryzacji OAuth2 (Client Credentials)
   - opcjonalnie `IZZYLEASE_STATE_FILE` – ścieżka do pliku z mapowaniem VIN → car_id (domyślnie `~/.izzy_uploader/state.json`)
3. Uruchom komendę synchronizacji:
   ```bash
   izzy-uploader sync data/vehicles.csv --close-missing --update-prices --json
   ```
   Raport procesu zostanie wypisany w formacie tekstowym lub JSON.

## Normalizacja danych partnerów
- Wbudowana warstwa czyszczenia (`normalizers.py`) konwertuje wartości typu `150.00` → `150`, usuwa znaczniki `NULL`, mapuje polskie nazwy (`osobowy`, `Na przednie koła`, `Automatyczna…`) na wartości wymagane przez API Izzylease oraz skraca daty z czasem do formatu `YYYY-MM-DD`.
- Brakujące `engineCode` uzupełniane są domyślną wartością `-`, aby przejść walidację API bez wprowadzania sztucznego opisu.
- Identyfikatory lokalizacji przekazywane przez partnerów można odwzorować na UUID salonów Izzylease w pliku `config/location_map.json` (wzorzec: `config/location_map.sample.json`). Ścieżkę do własnego pliku możesz wskazać zmienną `IZZYLEASE_LOCATION_MAP_FILE`.
- Brakujące mapowania są automatycznie pomijane (pole nie trafi do payloadu).

## Testy
Testy jednostkowe można uruchomić poleceniem:
```
pytest
```

Więcej szczegółów i roadmapę znajdziesz w `planning.md`.
