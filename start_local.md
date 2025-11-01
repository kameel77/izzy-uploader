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
   pip install -e .[dev]
   ```

## 5. Przygotowanie danych i konfiguracji
1. Przygotuj plik CSV z pojazdami. Dla testów możesz skopiować plik nagłówków z `_Planning/izzylease_lista_pol_import_pojazdow.csv` i wypełnić wiersze danymi.
2. Ustaw wymagane zmienne środowiskowe, aby aplikacja znała adres API i klucz dostępu:
   - Windows (PowerShell):
     ```powershell
     $Env:IZZYLEASE_API_BASE_URL = "https://twoj-serwer.izzylease.example"
     $Env:IZZYLEASE_API_KEY = "TWOJ_TAJNY_KLUCZ"
     ```
   - macOS/Linux:
     ```bash
     export IZZYLEASE_API_BASE_URL="https://twoj-serwer.izzylease.example"
     export IZZYLEASE_API_KEY="TWOJ_TAJNY_KLUCZ"
     ```
   Jeśli nie masz jeszcze danych dostępowych, poproś administratora platformy Izzylease.

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
