# Izzy Uploader – Public API

Dokument opisuje REST API udostępniane przez Izzy Uploader. Umożliwia:

1) synchronizację pojazdów z pliku CSV,  
2) pobranie raportu (utworzone/zmodyfikowane/usunięte pojazdy + błędy CSV),  
3) dodawanie zdjęć,  
4) usuwanie pojedynczych lub wszystkich znanych zdjęć,  
5) zastępowanie zdjęć (usuń istniejące i wgraj nowe).

## Podstawy
- Base URL: `https://<twoj-host>/api`
- Autoryzacja: brak dodatkowej warstwy (endpointy korzystają z poświadczeń Izzylease ustawionych po stronie serwera poprzez zmienne środowiskowe `IZZYLEASE_*`). Jeśli potrzebujesz ochrony, wystaw API za reverse proxy z auth (np. Basic/OAuth) lub dopisz middleware.
- Format: JSON; uploady w `multipart/form-data`.

## Endpoints

### Healthcheck
`GET /health`  
Odpowiedź: `{"status": "ok"}`.

### Synchronizacja pojazdów z CSV
`POST /vehicles/sync`  
Form-data:
- `file` (plik CSV) – wymagany.
- `close_missing` (bool opcjonalnie) – zamyka pojazdy spoza CSV.
- `update_prices` (bool opcjonalnie) – zachowane dla kompatybilności, ignorowane logicznie.

Przykład curl:
```bash
curl -X POST https://<host>/api/vehicles/sync \
  -F "file=@/path/vehicles.csv" \
  -F "close_missing=true"
```

Przykładowa odpowiedź (200):
```json
{
  "config_state_file": "/home/app/.izzy_uploader/state.json",
  "report": {
    "created": 2,
    "updated": 1,
    "price_updates": 0,
    "closed": 0,
    "errors": 0,
    "detail": {
      "created": [{"vin": "WDB...1", "car_id": "uuid-1"}],
      "updated": [{"vin": "WDB...2", "car_id": "uuid-2"}],
      "deleted": [],
      "errors": []
    }
  },
  "csv_errors": []
}
```

### Upload zdjęć pojazdu
`POST /vehicles/{car_id}/images`  
Form-data:  
- `main_image` (opcjonalnie)  
- `extra_images` (opcjonalnie, wielokrotne)  

Przykład:
```bash
curl -X POST https://<host>/api/vehicles/{car_id}/images \
  -F "main_image=@/path/main.jpg" \
  -F "extra_images=@/path/extra1.jpg" \
  -F "extra_images=@/path/extra2.jpg"
```

Odpowiedź (200):
```json
{
  "results": [
    {"label": "main_image", "status": "success", "image_id": "uuid-1", "message": "Uploaded"},
    {"label": "extra_image_1", "status": "success", "image_id": "uuid-2", "message": "Uploaded"}
  ]
}
```

### Usunięcie pojedynczego zdjęcia
`DELETE /vehicles/{car_id}/images/{image_id}`  
Odpowiedź 200:
```json
{"status": "success", "image_id": "uuid-2"}
```

### Usunięcie wielu lub wszystkich znanych zdjęć
`DELETE /vehicles/{car_id}/images`  
Body (JSON):
- `image_ids`: lista ID do usunięcia (opcjonalnie)
- `delete_all`: bool (opcjonalnie). Jeśli `true` i `image_ids` puste, użyje lokalnie zapamiętanych `imageId`.

Przykład (lista ID):
```bash
curl -X DELETE https://<host>/api/vehicles/{car_id}/images \
  -H "Content-Type: application/json" \
  -d '{"image_ids": ["uuid-1","uuid-2"]}'
```

Przykład (usuń wszystkie znane):
```bash
curl -X DELETE https://<host>/api/vehicles/{car_id}/images \
  -H "Content-Type: application/json" \
  -d '{"delete_all": true}'
```

Odpowiedź (200):
```json
{
  "results": [
    {"image_id": "uuid-1", "status": "success", "message": "Deleted image."},
    {"image_id": "uuid-2", "status": "error", "message": "Not found"}
  ]
}
```

### Zastąpienie zdjęć (usuń i wgraj nowe)
`POST /vehicles/{car_id}/images/replace`  
Form-data:
- `delete_all` (bool opcjonalnie) – usuń wszystkie znane, jeśli nie podano `image_ids`.
- `image_ids` (opcjonalnie, lista rozdzielana spacją/komami) – konkretne do usunięcia.
- `main_image` (opcjonalnie)
- `extra_images` (opcjonalnie, wielokrotne)

Przykład:
```bash
curl -X POST https://<host>/api/vehicles/{car_id}/images/replace \
  -F "delete_all=true" \
  -F "main_image=@/path/new_main.jpg" \
  -F "extra_images=@/path/new_extra.jpg"
```

Odpowiedź (200):
```json
{
  "deleted": [
    {"image_id": "uuid-old", "status": "success", "message": "Deleted image."}
  ],
  "uploaded": [
    {"label": "main_image", "status": "success", "image_id": "uuid-new", "message": "Uploaded"}
  ]
}
```

## Uwagi o stanie zdjęć
API używa lokalnego pliku stanu (domyślnie `~/.izzy_uploader/image_state.json`) do zapamiętywania `imageId` dodanych przez ten uploader.  
- `delete_all` działa w oparciu o te zapamiętane ID.  
- Jeśli zdjęcia dodano poza uploaderem, trzeba podać konkretne `image_ids`.

## Kody błędów
- 400 – brak wymaganych pól lub zły format danych.
- 500 – błąd wewnętrzny (np. błąd sieci przy wołaniu Izzylease). Komunikat w polu `error` lub `message`.

## Wymagania środowiskowe po stronie serwera
Ustaw zmienne:
- `IZZYLEASE_API_BASE_URL`
- `IZZYLEASE_CLIENT_ID`
- `IZZYLEASE_CLIENT_SECRET`
- `IZZYLEASE_STATE_FILE` (opcjonalnie, domyślnie `~/.izzy_uploader/state.json`)
- `IZZYLEASE_IMAGE_STATE_FILE` (opcjonalnie, domyślnie `~/.izzy_uploader/image_state.json`)

Serwer uruchom z `FLASK_APP=izzy_uploader_web.app flask run` (lub przez Gunicorn). Możesz wystawić reverse proxy (np. nginx) i dodać warstwę auth według potrzeb partnera.
