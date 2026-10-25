"""Find freely licensed photos for Specpoint on Wikimedia Commons.

    python specpoint/photos/fetch_photos.py search [key ...]   download up to 4 candidates per slot
    python specpoint/photos/fetch_photos.py pick KEY N [--caption "..."]   choose candidate N for a slot
    python specpoint/photos/fetch_photos.py apply              write photos.json into the website

Slots live in slots.json. Candidates go to photos/candidates/ (not committed) so a
person can look at them before picking. Only free licences are kept (public
domain, CC0, CC BY, CC BY-SA), and every photo keeps its author, licence and link
so the site can credit it.
"""
import html
import json
import os
import re
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SLOTS = json.loads((HERE / "slots.json").read_text(encoding="utf-8"))
CAND = HERE / "candidates"
IMG = HERE / "img"
MANIFEST = HERE / "photos.json"
SITE = HERE.parent / "index.html"
API = "https://commons.wikimedia.org/w/api.php"
UA = "SpecpointStudy/1.0 (free IGCSE revision site; github.com/Fletcher-eng/ChatDev)"
FREE = re.compile(r"^(public domain|pd\b|pd-|cc0|cc by(-sa)? \d(\.\d)?)", re.I)
WIDTH = 1200

CTX = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE") or None)


LAST = [0.0]


def get(url, tries=6):
    """Polite fetch: one request every 1.5 s, and wait as long as Wikimedia asks on 429."""
    for attempt in range(tries):
        wait = 1.5 - (time.time() - LAST[0])
        if wait > 0:
            time.sleep(wait)
        LAST[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt == tries - 1:
                raise
            pause = min(int(err.headers.get("Retry-After") or 30), 120) + 2
            print(f"   Wikimedia asked us to slow down, waiting {pause}s", flush=True)
            time.sleep(pause)


def plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def search(key, query, limit=4):
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": 12, "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size", "iiurlwidth": WIDTH,
    }
    data = json.loads(get(API + "?" + urllib.parse.urlencode(params)))
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    out = CAND / key
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    kept = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = plain(meta.get("LicenseShortName", {}).get("value"))
        if info.get("mime") not in ("image/jpeg", "image/png") or not FREE.match(lic):
            continue
        if info.get("width", 0) < 800:
            continue
        n = len(kept) + 1
        ext = ".png" if info["mime"] == "image/png" else ".jpg"
        (out / f"{n}{ext}").write_bytes(get(info["thumburl"]))
        kept.append({
            "n": n, "file": f"{n}{ext}", "title": page["title"], "license": lic,
            "artist": plain(meta.get("Artist", {}).get("value")) or "Unknown",
            "credit": plain(meta.get("Credit", {}).get("value")),
            "description": plain(meta.get("ImageDescription", {}).get("value"))[:300],
            "link": info.get("descriptionurl"), "size": [info.get("width"), info.get("height")],
        })
        if len(kept) >= limit:
            break
    (out / "meta.json").write_text(json.dumps(kept, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{key}: {len(kept)} candidates" + "".join(f"\n   {c['n']}. {c['title']} ({c['license']}, {c['artist'][:40]})" for c in kept))


def pick(key, n, caption=None):
    slot = next(s for s in SLOTS if s["key"] == key)
    cands = json.loads((CAND / key / "meta.json").read_text(encoding="utf-8"))
    c = next(c for c in cands if c["n"] == int(n))
    IMG.mkdir(exist_ok=True)
    ext = Path(c["file"]).suffix
    for old in IMG.glob(f"{key}.*"):
        old.unlink()
    shutil.copy(CAND / key / c["file"], IMG / f"{key}{ext}")
    photos = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    artist = re.sub(r"\s+", " ", c["artist"])[:60]
    photos[key] = {
        "src": f"img/{key}{ext}", "alt": slot["alt"], "caption": caption or slot["alt"],
        "credit": f"Photo: {artist}", "license": c["license"], "link": c["link"], "source": c["title"],
    }
    MANIFEST.write_text(json.dumps(photos, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{key}: picked {c['title']}")


def apply():
    photos = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    site = SITE.read_text(encoding="utf-8")
    block = re.compile(r"(/\* PHOTOS:START[^\n]*\*/\n).*?(\n/\* PHOTOS:END \*/)", re.S)
    if not block.search(site):
        raise SystemExit("PHOTOS markers not found in index.html")
    body = "const PHOTOS = " + json.dumps(photos, indent=2, ensure_ascii=False) + ";"
    SITE.write_text(block.sub(lambda m: m.group(1) + body + m.group(2), site), encoding="utf-8")
    print(f"Wrote {len(photos)} photos into {SITE.name}")


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else "help"), sys.argv[2:]
    if cmd == "search":
        for s in SLOTS:
            if not args or s["key"] in args:
                try:
                    search(s["key"], s["query"])
                except OSError as err:
                    raise SystemExit(f"Could not reach Wikimedia Commons ({err}). Allow commons.wikimedia.org and upload.wikimedia.org.")
    elif cmd == "pick":
        cap = args[args.index("--caption") + 1] if "--caption" in args else None
        pick(args[0], args[1], cap)
    elif cmd == "apply":
        apply()
    else:
        print(__doc__)
