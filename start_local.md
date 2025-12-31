# Jak uruchomić Izzy Uploader na własnym komputerze

Poniższa instrukcja prowadzi krok po kroku przez cały proces. Nie zakładamy wcześniejszego doświadczenia w pracy z Pythonem.

## 1. Przygotowanie komputera
1. **Sprawdź system.** Instrukcja została napisana dla Windows 10/11, macOS oraz Linux (Ubuntu). Jeśli używasz innego systemu, poszukaj, jak zainstalować na nim Pythona 3.10 lub nowszego.
2. **Zainstaluj Pythona:**
   - Wejdź na stronę <https://www.python.org/downloads/> i pobierz instalator dla swojego systemu.
   - Podczas instalacji na Windows zaznacz pole „Add Python to PATH” i dopiero potem kliknij „Install”.
3. **Zainstaluj Git (opcjonalnie, ale ułatwia pracę):**
   - Pobierz z <https://git-scm.com/downloads> i zainstaluj z ustawieniami domyślnymi.

## 2. Pobranie projektu
1. Otwórz terminal (PowerShell na Windows, Terminal na macOS/Linux).
2. Wybierz folder, w którym ma się znaleźć projekt, np. `Documents`:
   ```bash
   cd ~/Documents
   ```
3. Sklonuj repozytorium (jeśli używasz HTTPS):
   ```bash
   git clone https://github.com/<twoje-repo>/izzy-uploader.git
   ```
   Jeśli nie masz Gita, możesz pobrać paczkę ZIP z GitHuba i rozpakować ją w wybranym miejscu.
4. Przejdź do katalogu projektu:
   ```bash
   cd izzy-uploader
   ```

## 3. Utworzenie wirtualnego środowiska Pythona
Wirtualne środowisko pozwala zainstalować potrzebne biblioteki bez wpływu na resztę systemu.

1. Wykonaj komendę (jest taka sama dla Windows/macOS/Linux):
   ```bash
   python -m venv .venv
   ```
2. Aktywuj środowisko:
   - Windows (PowerShell):
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - macOS/Linux:
     ```bash
     source .venv/bin/activate
     ```
   Po poprawnej aktywacji w terminalu na początku wiersza pojawi się tekst `(.venv)`.

## 4. Instalacja zależności
1. Upewnij się, że środowisko jest aktywne.
2. Zainstaluj pakiet wraz z narzędziami deweloperskimi (do testów):
   ```bash
   pip install --upgrade pip
   pip install -e '.[dev]'
   ```

## 5. Przygotowanie danych i konfiguracji
1. Przygotuj plik CSV z pojazdami. Dla testów możesz skopiować plik nagłówków z `_Planning/izzylease_lista_pol_import_pojazdow.csv` i wypełnić wiersze danymi.
2. Ustaw wymagane zmienne środowiskowe, aby aplikacja znała adres API i dane do autoryzacji:
   - Windows (PowerShell):
     ```powershell
     $Env:IZZYLEASE_API_BASE_URL = "https://twoj-serwer.izzylease.example"
     $Env:IZZYLEASE_CLIENT_ID = "<client_id_z_pliku_konfiguracyjnego>"
     $Env:IZZYLEASE_CLIENT_SECRET = "<client_secret_z_pliku_konfiguracyjnego>"
     $Env:IZZYLEASE_STATE_FILE = "$env:USERPROFILE\\.izzy_uploader\\state.json"
     ```
   - macOS/Linux:
     ```bash
     export IZZYLEASE_API_BASE_URL="https://twoj-serwer.izzylease.example"
    export IZZYLEASE_CLIENT_ID="<client_id_z_pliku_konfiguracyjnego>"
    export IZZYLEASE_CLIENT_SECRET="<client_secret_z_pliku_konfiguracyjnego>"
    export IZZYLEASE_STATE_FILE="$HOME/.izzy_uploader/state.json"
    # opcjonalnie ścieżka do mapowania ID salonów partnera na UUID w Izzylease
    export IZZYLEASE_LOCATION_MAP_FILE="$PWD/config/location_map.json"
    # opcjonalnie ścieżka do lokalnego pliku z zapamiętanymi imageId
    export IZZYLEASE_IMAGE_STATE_FILE="$HOME/.izzy_uploader/image_state.json"
     ```
   Zmienna `IZZYLEASE_STATE_FILE` jest opcjonalna – jeśli jej nie ustawisz, aplikacja zapisze lokalne mapowanie VIN → car_id w katalogu domowym. Jeżeli nie masz jeszcze danych dostępowych (`client_id`/`client_secret`), poproś administratora platformy Izzylease.

   Jeżeli partner dostarcza własne identyfikatory salonów, przygotuj plik `config/location_map.json` (możesz skopiować wzorzec `config/location_map.sample.json`) i wypełnij go mapowaniem `"partner_id": "uuid_salon"`.

## 6a. Uruchomienie interfejsu webowego (opcjonalnie)
1. Zainstaluj zależności dodatkowe:
   ```bash
   pip install -e .[web]
   ```
2. Uruchom aplikację Flask:
   ```bash
   export FLASK_APP=izzy_uploader_web.app
   flask run
   ```
3. Wejdź na `http://127.0.0.1:5000`, wybierz plik CSV i pobierz raport JSON.
4. W zakładce „Mapowanie lokalizacji” możesz dopisywać pary `partner_id → UUID`. Zmiany trafiają do pliku z mapą lokalizacji (domyślnie `config/location_map.json`).
5. Dostępne jest też proste API (prefiks `/api`):
   - `GET /api/health` – sprawdzenie stanu.
   - `POST /api/vehicles/sync` – multipart z `file` (CSV), opcjonalnie `close_missing=true`.
   - `POST /api/vehicles/<car_id>/images` – multipart z `main_image` i/lub `extra_images`.
   - `DELETE /api/vehicles/<car_id>/images/<image_id>` – usuwa konkretne zdjęcie.
   - `DELETE /api/vehicles/<car_id>/images` – JSON `{"image_ids": [...]}`
     lub `{"delete_all": true}` (skorzysta z lokalnie zapamiętanych `imageId`).
   - `POST /api/vehicles/<car_id>/images/replace` – multipart; opcjonalnie `delete_all=true`
     lub `image_ids` (spacja/komy), plus nowe `main_image`/`extra_images`.

### Wymagane zmienne środowiskowe dla interfejsu webowego

Interfejs webowy wymaga tych samych zmiennych środowiskowych co wersja CLI (Command Line Interface). Upewnij się, że przed uruchomieniem aplikacji webowej ustawiłeś następujące zmienne:

**Zmienne obowiązkowe:**
- `IZZYLEASE_API_BASE_URL` - bazowy URL API (np. `https://twoj-serwer.izzylease.example`)
- `IZZYLEASE_CLIENT_ID` - ID klienta OAuth do autoryzacji
- `IZZYLEASE_CLIENT_SECRET` - sekret klienta OAuth do autoryzacji

**Zmienne opcjonalne:**
- `IZZYLEASE_TOKEN_URL` - URL do tokenu OAuth (domyślnie: `{API_BASE_URL}/oauth/token`)
- `IZZYLEASE_DEALER_ID` - identyfikator dealera
- `IZZYLEASE_STATE_FILE` - ścieżka do pliku stanu (domyślnie: `~/.izzy_uploader/state.json`)
- `IZZYLEASE_TIMEOUT` - timeout dla requestów w sekundach (domyślnie: 10)
- `IZZYLEASE_LOCATION_MAP_FILE` - ścieżka do pliku mapowania lokalizacji (domyślnie: `config/location_map.json`)
- `IZZYLEASE_IMAGE_STATE_FILE` - ścieżka do lokalnego pliku z zapamiętanymi `imageId` (domyślnie: `~/.izzy_uploader/image_state.json`)

Jeśli zmienne nie są ustawione, aplikacja wyświetli błąd o brakującej konfiguracji.

## 6. Uruchomienie narzędzia
Podstawowa komenda uruchamiająca proces synchronizacji wygląda tak:
```bash
izzy-uploader sync sciezka/do/pliku.csv --close-missing --update-prices --json
```
- `sciezka/do/pliku.csv` zamień na faktyczną ścieżkę do swojego pliku.
- Przełącznik `--close-missing` powoduje zamknięcie ofert, których nie ma w pliku.
- Przełącznik `--update-prices` aktualizuje ceny.
- Dodanie `--json` sprawia, że wynik pojawi się w czytelnej formie JSON; możesz pominąć ten przełącznik, aby zobaczyć zwykły tekst.

Po chwili zobaczysz raport z importu w terminalu. Jeśli pojawią się błędy, aplikacja wyświetli wskazówki co poprawić (np. brakujące kolumny w CSV albo nieustawione zmienne środowiskowe).

## 7. Uruchomienie testów (opcjonalnie)
Aby upewnić się, że wszystko działa poprawnie, uruchom testy jednostkowe:
```bash
pytest
```
Jeśli zobaczysz komunikat `collected ... passed`, wszystko jest w porządku.

## 8. Zakończenie pracy
Gdy skończysz, możesz dezaktywować środowisko poleceniem:
```bash
deactivate
```
Projekt możesz później ponownie uruchomić, aktywując środowisko (`source .venv/bin/activate` lub `.\.venv\Scripts\Activate.ps1`) i wznawiając pracę od kroku 6.

Gotowe! Masz działające środowisko Izzy Uploader na swoim komputerze.
