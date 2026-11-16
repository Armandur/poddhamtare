# CLAUDE.md - poddhamtare

Kodbasbeskrivning för Claude. Uppdatera vid arkitekturändringar.

## Vad projektet är

Hämtar podden Torsdagsdeppen (Kyrkans Tidning, via Acast) ur RSS och taggar
filerna ur flödets metadata, så att Airsonic och DSub visar rätt titel, ordning,
datum och omslag. Ska ersätta Flexget-tasken `Torsdagsdeppen` på TERVO2.

**Läge 2026-11-16:** utredning klar, inget byggt. Förslaget och fynden ligger i
backlog-docen "Utredning och förslag: poddhamtare" (`backlog doc list --project
poddhamtare`). Bygg inte förrän Rasmus beslutat om förslaget.

## Nuläget som ska ersättas

- Flexget (`wiserain/flexget`) kör på TERVO2, config i
  `/mnt/cache/appdata/FlexGet/config.yml`, task `Torsdagsdeppen`, varje timme
  (:57). Filer till `/mnt/user/media/Musik/Podcasts/Torsdagsdeppen/` som
  `ÅÅÅÅ-MM-DD - Titel.mp3`. Flexget rör inte taggarna.
- RSS: `https://feeds.acast.com/public/shows/690e68a1a17ebcde889789b9`.
- Acast levererar trasiga ID3-taggar: `TIT2` är produktionens filnamn
  ("Untitled", "2026-04-28--t07-23-09am--guest354719--johan-garde"), inget
  `TRCK`, inget `APIC`, `TDRC` bara år. Filerna sys ihop med reklam per
  nedladdning (`stitcher2.acast.com/livestitches`), så två hämtningar av samma
  avsnitt ger olika bytes.
- Airsonic (`musik`-containern) läser hela `Musik/` som musikmapp. Allt under
  `Podcasts/` får `TYPE=PODCAST` oavsett genre. DSub läser inte filerna utan
  Airsonics `MEDIA_FILE`-rad via Subsonic-API:t. Airsonic skannar kl. 03:00.

## Läsåtkomst från ubuntu-ai

`/mnt/tervo2/media` och `/mnt/tervo2/appdata` är NFS-monterade **read-only**.
Airsonics databas finns som klartext i
`/mnt/tervo2/appdata/airsonic-advanced/db/airsonic.script` (HSQLDB). Skriva
till TERVO2 kräver Rasmus ok, ingen direkt ssh.

## Förebild

`~/workspace/kafferepet-dl` (backlog-alias `kafferepet`): taggning med mutagen,
namngivning, RSS-läsning och schemaläggning. Ändra inget där.

## Stack (planerad)

Python 3.12, `mutagen`, `httpx`, `Pillow`. Ingen webb-UI i v1. Docker på
TERVO2 via dockyard. Venv: `python3 -m venv .venv`.
