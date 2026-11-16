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
| `schema` | kör `hamta` enligt `CRON_SCHEDULE` |

Filnamn: `ÅÅÅÅ-MM-DD - 0045 - Titel.mp3`. Titeltagg: `0045 - Titel`.

## Deploy på Unraid (TERVO2)

Image: `ghcr.io/armandur/poddhamtare:latest`. Ingen port.

| Container | Host | Läge |
|---|---|---|
| `/podcasts/torsdagsdeppen` | `/mnt/user/media/Musik/Podcasts/Torsdagsdeppen` | rw |
| `/state` | `/mnt/cache/appdata/poddhamtare` | rw |

| Variabel | Värde |
|---|---|
| `TZ` | `Europe/Stockholm` |
| `CRON_SCHEDULE` | `30 */3 * * *` |
| `PUID` / `PGID` | `99` / `100` |

Containern kopierar standardkonfigen till `/state/config.yaml` vid första
start. Post-arguments styr läget: tomt ger schemat, `retag` ger en
torrkörning och `retag --apply` gör den skarpa omtaggningen.

### Övertagande från Flexget

1. Kör containern med post-argument `retag` och läs loggen.
2. Stäng av Flexget-tasken `Torsdagsdeppen` i `config.yml`.
3. Kör `retag --apply`. Ta sedan bort post-argumentet, så startar schemat.
4. Efter Airsonics skanning kl. 03:00: kontrollera i DSub och uppdatera vyn
   om den visar gamla titlar.
