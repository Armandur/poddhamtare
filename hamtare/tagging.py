"""ID3-taggning med mutagen. Rensar ALLA befintliga ramar först, eftersom Acasts
taggar är skräp (TIT2 = produktionens arbetsfilnamn)."""
import hashlib
import json

from mutagen.id3 import (APIC, COMM, ID3, TALB, TCON, TDRC, TIT2, TPE1, TRCK,
                         TXXX, ID3NoHeaderError)

GUID_DESC = "PODCAST_GUID"
FINGERPRINT_DESC = "PODDHAMTARE"


def fingerprint(fields):
    """Kort hash av önskade taggvärden. Ändras den, taggas filen om."""
    blob = json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha1(blob).hexdigest()[:16]


def write(path, *, title, album, artist, genre, date, track, comment, guid,
          cover_jpeg, fp):
    tags = ID3()
    tags.add(TIT2(encoding=3, text=[title]))
    tags.add(TALB(encoding=3, text=[album]))
    tags.add(TPE1(encoding=3, text=[artist]))
    tags.add(TCON(encoding=3, text=[genre]))
    tags.add(TDRC(encoding=3, text=[date]))
    tags.add(TRCK(encoding=3, text=[str(track)]))
    if comment:
        tags.add(COMM(encoding=3, lang="swe", desc="", text=[comment]))
    tags.add(TXXX(encoding=3, desc=GUID_DESC, text=[guid]))
    tags.add(TXXX(encoding=3, desc=FINGERPRINT_DESC, text=[fp]))
    if cover_jpeg:
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover",
                      data=cover_jpeg))
    # Albumartist (TPE2) lämnas tom, som i kafferepet-dl (spec F4).
    tags.save(path, v2_version=4, v1=0)


def read_ids(path):
    """(guid, fingerprint) ur filens TXXX-ramar, eller (None, None)."""
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        return None, None
    return _txxx(tags, GUID_DESC), _txxx(tags, FINGERPRINT_DESC)


def _txxx(tags, desc):
    frame = tags.get(f"TXXX:{desc}")
    return str(frame.text[0]) if frame and frame.text else None
