# Jak uruchomić Izzy Uploader na serwerze VPS Hetzner

Ta instrukcja zakłada, że masz aktywny serwer VPS w Hetznerze (np. z systemem Ubuntu 22.04) oraz dostęp do konta root poprzez SSH. Wszystkie kroki opisano możliwie prostym językiem.

## 1. Połączenie z serwerem
1. Otwórz terminal na swoim komputerze.
2. Połącz się z serwerem poleceniem (adres IP znajdziesz w panelu Hetznera):
   ```bash
   ssh root@ADRES_IP_Twojego_Serwera
   ```
   - Jeśli to pierwsze połączenie, potwierdź pytanie o zaufanie (`yes`).
   - Wpisz hasło root podane przez Hetznera (możesz je wkleić prawym przyciskiem myszy w terminalu).

## 2. Aktualizacja systemu
Po zalogowaniu uruchom standardowe aktualizacje:
```bash
apt update && apt upgrade -y
```
Dzięki temu wszystkie pakiety będą w najnowszych wersjach.

## 3. Instalacja narzędzi systemowych
Zainstaluj Git, Pythona i narzędzia do kompilacji (mogą być potrzebne przy instalacji bibliotek):
```bash
apt install -y git python3 python3-venv python3-pip build-essential
```

## 4. Utworzenie dedykowanego użytkownika (zalecane)
Aby nie pracować cały czas jako root, warto stworzyć osobne konto. Jeśli chcesz pominąć ten krok, przejdź do punktu 5.
```bash
adduser izzy
usermod -aG sudo izzy
su - izzy
```
Ostatnia komenda przełącza na nowego użytkownika.

## 5. Pobranie projektu na serwer
1. Wybierz katalog, w którym ma działać aplikacja, np. domowy użytkownika:
   ```bash
   cd ~
   ```
2. Sklonuj repozytorium (podstaw poprawny adres HTTPS/SSH):
   ```bash
   git clone https://github.com/<twoje-repo>/izzy-uploader.git
   cd izzy-uploader
   ```

## 6. Przygotowanie środowiska Pythona
1. Utwórz wirtualne środowisko:
   ```bash
   python3 -m venv .venv
   ```
2. Aktywuj je:
   ```bash
   source .venv/bin/activate
   ```
3. Zaktualizuj `pip` i zainstaluj projekt z zależnościami (CLI + UI):
   ```bash
   pip install --upgrade pip
   pip install -e '.[dev,web]'
   ```

## 7. Konfiguracja dostępu do API Izzylease
1. Ustal wartości zmiennych środowiskowych (dane powinieneś otrzymać od Izzylease):
   ```bash
   export IZZYLEASE_API_BASE_URL="https://twoj-serwer.izzylease.example"
   export IZZYLEASE_CLIENT_ID="TWOJ_CLIENT_ID"
   export IZZYLEASE_CLIENT_SECRET="TWOJ_CLIENT_SECRET"
   # opcjonalnie ścieżka do pliku stanu i mapowania lokalizacji
   export IZZYLEASE_STATE_FILE="$HOME/.izzy_uploader/state.json"
   export IZZYLEASE_LOCATION_MAP_FILE="$HOME/.izzy_uploader/location_map.json"
   ```
2. Jeśli chcesz, aby były ustawione po każdym logowaniu, dopisz te linie do pliku `~/.bashrc`:
   ```bash
   echo 'export IZZYLEASE_API_BASE_URL="https://twoj-serwer.izzylease.example"' >> ~/.bashrc
   echo 'export IZZYLEASE_CLIENT_ID="TWOJ_CLIENT_ID"' >> ~/.bashrc
   echo 'export IZZYLEASE_CLIENT_SECRET="TWOJ_CLIENT_SECRET"' >> ~/.bashrc
   echo 'export IZZYLEASE_STATE_FILE="$HOME/.izzy_uploader/state.json"' >> ~/.bashrc
   echo 'export IZZYLEASE_LOCATION_MAP_FILE="$HOME/.izzy_uploader/location_map.json"' >> ~/.bashrc
   source ~/.bashrc
   ```

## 8. Przygotowanie pliku CSV
1. Prześlij plik CSV na serwer (np. przy użyciu `scp`):
   ```bash
   scp /sciezka/do/twojego_pliku.csv izzy@ADRES_IP_Twojego_Serwera:/home/izzy/izzy-uploader/data.csv
   ```
   Zmienna `izzy` to nazwa użytkownika, a `data.csv` to nazwa pliku na serwerze.
2. Upewnij się, że plik ma nagłówki zgodne z `_Planning/izzylease_lista_pol_import_pojazdow.csv`.

## 9. Uruchomienie synchronizacji (CLI)
Będąc w katalogu projektu i z aktywnym środowiskiem (`source .venv/bin/activate`):
```bash
izzy-uploader sync data.csv --close-missing --update-prices --json
```
- Jeśli plik CSV leży w innym miejscu, podaj pełną ścieżkę (np. `/home/izzy/izzy-uploader/import/auta.csv`).
- Raport z działania pojawi się od razu w terminalu.

## 10. Uruchomienie interfejsu webowego (opcjonalne)
1. Upewnij się, że zależności webowe są zainstalowane (patrz pkt 6).
2. Włącz aplikację Flask:
   ```bash
   export FLASK_APP=izzy_uploader_web.app
   flask run --host 0.0.0.0 --port 8000
   ```
   - `--host 0.0.0.0` umożliwia dostęp z zewnątrz (np. przez przeglądarkę),
   - `--port 8000` to przykładowa wartość – możesz ustawić inną.
3. W przeglądarce otwórz `http://ADRES_IP_Twojego_Serwera:8000`.
4. Formularz pozwala załadować CSV, uruchomić synchronizację, obejrzeć i pobrać raport.
5. Zakładka „Mapowanie lokalizacji” umożliwia dopisywanie par `partner_id → UUID` – zmiany trafiają do pliku `config/location_map.json` (lub wskazanego przez `IZZYLEASE_LOCATION_MAP_FILE`).
6. Aby wystawić UI produkcyjnie, rozważ użycie Gunicorna i nginx, np.:
   ```bash
   gunicorn izzy_uploader_web:create_app --bind 0.0.0.0:8000
   ```

## 11. Automatyzacja synchronizacji (opcjonalnie)
Jeśli chcesz uruchamiać synchronizację cyklicznie (np. codziennie o 2:00):
1. Otwórz edytor crona:
   ```bash
   crontab -e
   ```
2. Dodaj linijkę (przystosuj ścieżki do swojej lokalizacji):
   ```cron
   0 2 * * * source /home/izzy/izzy-uploader/.venv/bin/activate && cd /home/izzy/izzy-uploader && izzy-uploader sync /home/izzy/izzy-uploader/data.csv --close-missing --update-prices --json >> /home/izzy/izzy-uploader/logs.txt 2>&1
   ```
   Dzięki temu wynik działania trafi do pliku `logs.txt`.

## 12. Zakończenie pracy
- Aby wylogować się z serwera, wpisz `exit`.
- Przed wylogowaniem możesz dezaktywować środowisko Pythona poleceniem `deactivate`.

Po wykonaniu powyższych kroków Izzy Uploader działa na Twoim serwerze VPS Hetzner – zarówno w trybie CLI, jak i poprzez prosty interfejs webowy.
