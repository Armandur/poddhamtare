# poddhamtare

Hämtar podden Torsdagsdeppen ur RSS och taggar filerna ur flödet, så att
Airsonic och DSub visar rätt titel, ordning och omslag. Ersätter
Flexget-tasken för podden. Acast levererar filerna med trasiga taggar, där
titeln oftast är ett arbetsfilnamn som "Untitled".

## Köra lokalt

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
STATE_DIR=./tmp/state .venv/bin/python run.py --config config.yaml retag      # torrkörning
STATE_DIR=./tmp/state .venv/bin/python run.py --config config.yaml retag --apply
STATE_DIR=./tmp/state .venv/bin/python run.py --config config.yaml hamta --dry-run
.venv/bin/python -m pytest -q && .venv/bin/ruff check .
```

| Kommando | Gör |
|---|---|
| `hamta [--dry-run] [--limit N]` | hämtar nya avsnitt och taggar om filer där flödet ändrats |
| `retag [--apply]` | tar in gamla filer utan guid-tagg: matchar, taggar om och byter namn. Utan `--apply` blir det en torrkörning |

Webbgränssnittet lokalt: `CRON_SCHEDULE='0 0 1 1 *' .venv/bin/uvicorn app.main:app --port PORT`.

Filnamn: `ÅÅÅÅ-MM-DD - 0045 - Titel.mp3`. Titeltagg: `0045 - Titel`.

## Deploy på Unraid (TERVO2)

Image: `ghcr.io/armandur/poddhamtare:latest`.

Webbgränssnittet visar schema, avsnitt, körningshistorik med logg och en
livelogg. Knappen "Kör" startar en hämtning eller en torrkörning. Sidan har
ingen inloggning, så exponera den inte utanför hemnätet.

| Port i containern | Host |
|---|---|
| `8000` | valfri ledig port |

| Container | Host | Läge |
|---|---|---|
| `/podcasts/torsdagsdeppen` | `/mnt/user/media/Musik/Podcasts/Torsdagsdeppen` | rw |
| `/state` | `/mnt/cache/appdata/poddhamtare` | rw |

| Variabel | Värde |
|---|---|
| `TZ` | `Europe/Stockholm` |
| `CRON_SCHEDULE` | `30 */3 * * *` |
| `PUID` / `PGID` | `99` / `100` |
| `RETAG_ON_START` | tomt i drift. `dry` eller `apply` vid övertagandet, se nedan |

Containern kopierar standardkonfigen till `/state/config.yaml` vid första
start. Den startar alltid webbgränssnittet, som också kör schemat. `hamta` vägrar köra tills
`retag --apply` har skapat state, så en felstavad montering ger inga
massnedladdningar.

### Övertagande från Flexget

Dockyard kan inte sätta post-argument. Övertagandet styrs därför med env
`RETAG_ON_START`, som dockyard kan ändra med PATCH.

1. Skapa containern med `RETAG_ON_START=dry`. Loggen ska visa 47 `TAGGA`.
   Står det 47 `SAKNAS` är monteringen fel.
2. Stäng av Flexget-tasken `Torsdagsdeppen` i Flexgets `config.yml`.
3. Sätt `RETAG_ON_START=apply`, som startar om containern. Den taggar om
   och byter namn på filerna. Töm sedan variabeln.
4. Efter Airsonics skanning kl. 03:00, eller en manuell skanning: kontrollera
   i DSub och uppdatera vyn om den visar gamla titlar.
