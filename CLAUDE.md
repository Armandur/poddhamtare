# CLAUDE.md - poddhamtare

Kodbasbeskrivning för Claude. Uppdatera i samma commit när strukturen ändras.

## Vad projektet är

Hämtar podden Torsdagsdeppen (Kyrkans Tidning, via Acast) ur RSS och taggar
filerna ur flödets metadata, så att Airsonic och DSub visar rätt titel, ordning
och omslag. Ersätter Flexget-tasken `Torsdagsdeppen` på TERVO2. Konfigen är en
lista över shows, så fler poddar kan flyttas hit senare.

Utredning och beslut: backlog-docen "Utredning och förslag: poddhamtare" och
backlog memory i projektet `poddhamtare` (besluten från beslutsvyn 2026-11-16).

## Stack

Python 3.12, `mutagen` (ID3), `httpx`, `Pillow` (omslag), `PyYAML`, `croniter`.
Ingen webb-UI, ingen databas. Docker-image `ghcr.io/armandur/poddhamtare`.

## Filstruktur

```
run.py              CLI: hamta | retag | schema. Lås, loggning, exitkod
config.yaml         standardkonfig (vid deploy: /state/config.yaml)
hamtare/
  config.py         config.yaml -> Config/Show
  feed.py           RSS -> Feed/Episode (stdlib-XML), HTML-beskrivning -> text
  naming.py         filnamn 'ÅÅÅÅ-MM-DD - 0045 - Titel.mp3', titeltagg, matchnyckel
  state.py          STATE_DIR/<slug>.json: guid -> löpnummer, omslags-URL
  plan.py           skannar mappen, matchar filer mot flödet, bygger åtgärdslista
  execute.py        utför planen via dold .part-fil + os.replace, cover.jpg
  tagging.py        skriver alla ID3-ramar på nytt, läser guid och fingeravtryck
  cover.py          hämtar och skalar omslag, cache i STATE_DIR/covers
  lock.py           flock så schema och manuell körning inte krockar
tests/              pytest, tests/data/tyst.mp3 är en 2 s tyst fixtur
.githooks/pre-push  ruff + pytest (git config core.hooksPath .githooks)
Dockerfile, entrypoint.sh, .github/workflows/docker-publish.yml
```

## Designbeslut

- **Spärrar i `hamta`:** vägrar utan state-fil (kör `retag --apply` först) och
  utan målmapp, så en felstavad montering inte ger 47 nya hämtningar.
- **Filer känns igen på `TXXX:PODCAST_GUID`.** `hamta` vägrar köra om mappen har
  mp3:or utan den taggen, annars hämtas avsnitten en gång till. Gamla filer tas
  in med `retag`, som matchar på datum (±1 dygn, Flexget tog datumet i UTC) och
  titel, och avbryter om matchningen inte blir exakt en fil per avsnitt.
- **Löpnummer, inte flödets `itunes:episode`.** Flödet har två nr 10 och två nr 31.
  `State.assign_numbers` delar ut nummer i publiceringsordning första gången ett
  guid syns och ändrar dem aldrig.
- **Titel och filnamn som kafferepet-dl:** `TIT2 = '0045 - Titel'`,
  `ÅÅÅÅ-MM-DD - 0045 - Titel.mp3`, datum i Europe/Stockholm. `TPE2` lämnas tom.
- **Alla ID3-ramar skrivs om.** Acasts taggar är skräp. ID3 v2.4, ingen v1.
- **Fingeravtryck i `TXXX:PODDHAMTARE`.** Hash av önskade taggvärden och
  omslags-URL. Ändras titeln i flödet, taggas filen om och byter namn. Misslyckas
  omslaget skrivs ett tomt avtryck, så nästa körning försöker igen.
- **Atomärt:** hämtning och omtaggning går via `.<hash>.part` i målmappen och
  `os.replace`. Airsonic och podderi ser aldrig en halv fil. Ljudet rörs inte.
- **Omslag:** `cover.jpg` (kanalbilden) i mappen för Airsonic, plus `APIC` per
  avsnitt, nedskalat till 1000 px.
- **SIGTERM** i schemaläget ger `sys.exit`, annars väntar `docker stop` (PID 1).

## Fakta om omgivningen

- Acast syr in ny reklam per nedladdning (`livestitches`). Omhämtning ger ny fil.
- Airsonic (`musik`) ger allt under `Musik/Podcasts/` typen PODCAST, lagrar bara
  år (ingen datumkolumn) och skannar 03:00. DSub visar Airsonics rad.
- ubuntu-ai har bara read-only NFS mot TERVO2: `/mnt/tervo2/media`,
  `/mnt/tervo2/appdata`. Torrkörning mot riktiga mappen går därifrån.

## Miljövariabler

`CONFIG_PATH` (default `config.yaml`, i containern `/state/config.yaml`),
`STATE_DIR` (`/state`), `CRON_SCHEDULE` (`30 */3 * * *`), `TZ`
(`Europe/Stockholm`), `PUID`/`PGID` (99/100), `RUN_ONCE`, `RETAG_ON_START`
(`dry`/`apply`: kör `retag` före schemat, för övertagande via dockyard-PATCH).

## Vanliga ändringar

- **Ny podd:** lägg till en post under `shows:` i `/state/config.yaml` och en
  rw-mount för mappen. Har mappen gamla filer: kör `retag` först.
- **Nytt filnamnsmönster:** `naming.filename` + prov. Befintliga filer byter
  namn vid nästa körning, eftersom fingeravtrycket inte påverkas men namnet skiljer.
