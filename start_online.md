# Uruchomienie Izzy Uploader na VPS Hetzner (środowisko wieloaplikacyjne)

Poniższa procedura pomaga przygotować nowy serwer VPS (np. Hetzner CX/CP) tak, aby można było równolegle hostować wiele aplikacji w różnych technologiach. Instrukcja zakłada Ubuntu 22.04 LTS oraz dostęp do konta `root` przez SSH.

---

## 1. Dostęp i podstawowe bezpieczeństwo

1. **Połączenie SSH**  
   ```bash
   ssh root@ADRES_IP_SERWERA
   ```
2. **Aktualizacje i podstawowe pakiety**  
   ```bash
   apt update && apt upgrade -y
   apt install -y build-essential curl git htop unzip ufw
   ```
3. **Firewall UFW**  
   ```bash
   ufw allow OpenSSH
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw enable
   ```
4. **Utworzenie konta operatorskiego** (bez pracy na `root`):  
   ```bash
   adduser deploy
   usermod -aG sudo deploy
   ```
   Następnie dodaj swój publiczny klucz do `~deploy/.ssh/authorized_keys` i zabroń logowania hasłem (edycja `/etc/ssh/sshd_config`, parametry `PasswordAuthentication no`, potem `systemctl reload sshd`).

---

## 2. Wspólna infrastruktura dla wielu aplikacji

W środowisku, gdzie planujemy uruchamiać wiele projektów, warto przygotować wspólne komponenty:

1. **Docker + Docker Compose**  
   ```bash
   apt install -y ca-certificates gnupg
   install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
     $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
   apt update
   apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   usermod -aG docker deploy
   ```
   (wyloguj / zaloguj się ponownie, aby grupa zaczęła działać).

2. **Reverse proxy + certyfikaty**
   - Zainstaluj Traefik lub Nginx jako reverse proxy (poniższy przykład używa Traefika w Dockerze).
   - Stwórz katalog `/srv/infra/traefik` i dodaj `docker-compose.yml`, który wystawi porty 80/443 oraz automatyczne certyfikaty Let's Encrypt. Używaj etykiet Traefika w każdej aplikacji, aby routować ruch.

3. **Struktura katalogów**  
   ```
   /srv
     ├─ infra/         # Dodatkowe usługi (traefik, monitoring, logowanie)
     ├─ apps/
     │   └─ izzy-uploader/
     └─ secrets/       # Pliki .env, certyfikaty
   ```

4. **Monitoring / logi (opcjonalnie)**
   - Zainstaluj `fail2ban`, `prometheus-node-exporter`, `netdata` lub inne narzędzia zależnie od potrzeb.

---

## 3. Przygotowanie aplikacji Izzy Uploader

> Poniższe kroki wykonuj jako użytkownik `deploy` (lub inny utworzony w kroku 1.4), który ma dostęp do repozytorium.

### 3.1 Klonowanie repozytorium
```bash
ssh deploy@ADRES_IP_SERWERA
mkdir -p /srv/apps
cd /srv/apps
git clone https://github.com/<twoje-repo>/izzy-uploader.git
cd izzy-uploader
```

### 3.2 Konfiguracja środowiska
Skopiuj plik `.env.example` i uzupełnij wartości:
```bash
cp .env.example .env
```
Kluczowe zmienne:
- `IZZYLEASE_API_BASE_URL`, `IZZYLEASE_CLIENT_ID`, `IZZYLEASE_CLIENT_SECRET`
- Ścieżki do plików stanu (np. `/srv/data/izzy-uploader/state.json`)
- Opcjonalnie konfiguracja SMTP dla powiadomień (jeśli przewidziano)

Najbezpieczniej przechowywać `.env` w `/srv/secrets/izzy-uploader.env` i odwoływać się do niego z docker-compose / systemd.

### 3.3 Wybór sposobu uruchomienia

#### Opcja A: Docker Compose (rekomendowana)

Repo zawiera gotowy `Dockerfile`, `.dockerignore` oraz przykładowy `docker-compose.yml`.

1. Skonfiguruj zmienne środowiskowe:
   ```bash
   cp docker/.env.example docker/.env
   nano docker/.env  # uzupełnij dane API i sekret
   ```
2. Jeśli korzystasz z Traefika, upewnij się, że kontener jest w tej samej sieci:
   ```bash
   docker network create traefik  # jeśli jeszcze nie istnieje
   # w docker-compose.yml dodaj sekcję networks:
   # networks:
   #   - traefik
   # networks:
   #   traefik:
   #     external: true
   ```
3. Budowa i uruchomienie:
   ```bash
   docker compose build
   docker compose up -d
   ```
4. Domyślnie aplikacja nasłuchuje na porcie `8000`. Etykiety Traefika w pliku Compose kierują ruch na subdomenę `uploader.twojadomena.pl`, ale możesz je dostosować lub użyć własnego reverse proxy/nginx.

#### Opcja B: Systemd + Python venv

1. Zainstaluj zależności w wirtualnym środowisku:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -e '.[web]'
   ```
2. Stwórz plik `/etc/systemd/system/izzy-uploader.service`:
   ```ini
   [Unit]
   Description=Izzy Uploader
   After=network.target

   [Service]
   WorkingDirectory=/srv/apps/izzy-uploader
   EnvironmentFile=/srv/secrets/izzy-uploader.env
   ExecStart=/srv/apps/izzy-uploader/.venv/bin/gunicorn izzy_uploader_web:create_app --bind 127.0.0.1:8000
   Restart=always
   User=deploy

   [Install]
   WantedBy=multi-user.target
   ```
3. Uruchom i dodaj reverse proxy w Nginx/Traefik, aby kierować ruch z portu 443.

---

## 4. Dostęp CLI i automatyzacja

1. **Manualne uruchomienie synchronizacji** (w kontenerze lub venv):
   ```bash
   izzy-uploader sync /srv/data/izzy-uploader/import.csv --close-missing --update-prices
   ```
2. **Cron (harmonogram)**  
   Użytkownik `deploy` może dodać wpis:
   ```bash
   crontab -e
   ```
   ```
   0 2 * * * /usr/bin/docker compose -f /srv/apps/izzy-uploader/docker-compose.yml run --rm izzy-uploader \
     izzy-uploader sync /data/import.csv --close-missing --update-prices >> /srv/log/izzy-uploader/sync.log 2>&1
   ```
   (Dostosuj komendę do wybranego sposobu uruchomienia.)

3. **Backup plików**  
   - `/srv/data/izzy-uploader` (CSV, raporty, stan).
   - `/srv/secrets/izzy-uploader.env`.
   Rozważ użycie Hetzner Storage Box + `restic` / `rclone`.

---

## 5. Monitoring i logi

1. **Logi aplikacji**:  
   - Docker: `docker compose logs -f izzy-uploader`
   - Systemd: `journalctl -u izzy-uploader -f`
2. **Alerty**:  
   - Zainstaluj `promtail` + Grafana Loki lub prostsze narzędzia typu `logrotate`.
3. **Testy działania**:  
   - Endpoint health-check (np. `/health` jeśli zaimplementowany).
   - Monitor cronów (np. `healthchecks.io`).

---

## 6. Dodawanie kolejnych aplikacji

1. Każda nowa usługa trafia do `/srv/apps/<nazwa>` i ma osobny `.env` w `/srv/secrets`.
2. Reużywaj Traefika / reverse proxy – dzięki temu certyfikaty i routingi są konfigurowane w jednym miejscu.
3. Standaryzuj nazwy usług, logów, portów i sieci dockerowych.
4. Dokumentuj w `/srv/docs` wszystkie kroki dla przyszłych członków zespołu.

---

## 7. Lista kontrolna po wdrożeniu

- [ ] Użytkownik `deploy` ma dostęp SSH i sudo.
- [ ] Firewall (UFW) aktywny, porty 80/443/22 dozwolone.
- [ ] Traefik/Gunicorn/Nginx działają i obsługują certyfikaty.
- [ ] Izzy Uploader startuje (systemd lub docker) i reaguje na `izzy-uploader sync`.
- [ ] Zmiennych środowiskowych nie ma w repozytorium, trzymane są w `/srv/secrets`.
- [ ] Zdefiniowany backup danych (`/srv/data`, `/srv/secrets`).
- [ ] Dokumentacja wewnętrzna uzupełniona (np. `README.md` w `/srv/apps/izzy-uploader`).
- [ ] Kontrola logów: `journalctl`, `docker logs`, monitoring.

Po wykonaniu powyższych kroków serwer VPS Hetzner jest gotowy do hostowania wielu aplikacji, a Izzy Uploader działa w produkcyjnym środowisku z centralnym zarządzaniem konfiguracją i ruchem.
