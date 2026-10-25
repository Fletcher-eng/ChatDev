"""Find freely licensed photos for Specpoint.

    python specpoint/photos/fetch_photos.py search [key ...] [--openverse]   download up to 4 candidates per slot
    python specpoint/photos/fetch_photos.py pick KEY N [--caption "..."]   choose candidate N for a slot
    python specpoint/photos/fetch_photos.py apply              write photos.json into the website

Photos come from Wikimedia Commons, or from Openverse (Flickr and other open
collections) with --openverse. Slots live in slots.json. Candidates go to
photos/candidates/ (not committed) so a person can look at them before picking. Only free licences are kept (public
domain, CC0, CC BY, CC BY-SA), and every photo keeps its author, licence and link
so the site can credit it.
"""
import html
import json
import os
import re
import shutil
import ssl
import subprocess
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
OPENVERSE = "https://api.openverse.org/v1/images/"
UA = "SpecpointStudy/1.0 (free IGCSE revision site; github.com/Fletcher-eng/ChatDev)"
FREE = re.compile(r"^(public domain|pd\b|pd-|cc0|cc by(-sa)? \d(\.\d)?)", re.I)
# Wikimedia only serves its standard thumbnail widths without throttling: https://w.wiki/GHai
WIDTH = 1280

CTX = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE") or None)


LAST = [0.0]


def get(url, tries=6):
    """Polite fetch: one request every 1.5 s, wait as long as the server asks on 429, retry slow replies."""
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
            print(f"   The server asked us to slow down, waiting {pause}s", flush=True)
            time.sleep(pause)
        except (TimeoutError, urllib.error.URLError):
            if attempt >= 2:
                raise
            print("   Slow response, trying again", flush=True)
            time.sleep(10)


def plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def commons(query):
    """Freely licensed photos on Wikimedia Commons, best match first."""
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": 12, "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size", "iiurlwidth": WIDTH,
    }
    data = json.loads(get(API + "?" + urllib.parse.urlencode(params)))
    for page in sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99)):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        if info.get("mime") not in ("image/jpeg", "image/png"):
            continue
        yield {
            "title": page["title"], "license": plain(meta.get("LicenseShortName", {}).get("value")),
            "artist": plain(meta.get("Artist", {}).get("value")) or "Unknown",
            "credit": plain(meta.get("Credit", {}).get("value")),
            "description": plain(meta.get("ImageDescription", {}).get("value"))[:300],
            "link": info.get("descriptionurl"), "size": [info.get("width"), info.get("height")],
            "url": info.get("thumburl"),
        }


def openverse(query):
    """Openverse indexes openly licensed photos from Flickr, museums and photographers' sites."""
    params = {"q": query, "license": "by,by-sa,cc0,pdm", "mature": "false", "page_size": 12,
              "excluded_source": "wikimedia"}  # Commons photos come through the Commons search instead
    data = json.loads(get(OPENVERSE + "?" + urllib.parse.urlencode(params)))
    for r in data.get("results", []):
        lic = {"pdm": "Public domain", "cc0": "CC0"}.get(r["license"]) or f"CC {r['license'].upper()} {r.get('license_version') or ''}".strip()
        yield {
            "title": r.get("title") or "Untitled", "license": lic, "artist": r.get("creator") or "Unknown",
            "credit": f"via {r.get('provider', 'Openverse')}", "description": "",
            "link": r.get("foreign_landing_url"), "size": [r.get("width") or 0, r.get("height") or 0],
            "url": r["url"],
        }


def save_image(data, stem):
    """Write a download as a web friendly JPEG (or PNG) no wider than WIDTH, whatever format it arrived in."""
    ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
    raw = stem.with_suffix(".download")
    raw.write_bytes(data)
    if shutil.which("convert"):
        subprocess.run(["convert", f"{raw}[0]", "-auto-orient", "-resize", f"{WIDTH}x{WIDTH}>", "-strip",
                        "-quality", "82", str(stem.with_suffix(ext))], check=True)
        raw.unlink()
    elif data[:2] == b"\xff\xd8" or ext == ".png":
        raw.rename(stem.with_suffix(ext))
    else:
        raw.unlink()
        raise ValueError("not a JPEG or PNG, and ImageMagick is not installed to convert it")
    return f"{stem.name}{ext}"


def search(key, query, source="commons", min_width=800, limit=4):
    out = CAND / key
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    kept = []
    for c in (openverse if source == "openverse" else commons)(query):
        if not FREE.match(c["license"]) or (c["size"][0] or 0) < min_width:
            continue
        n = len(kept) + 1
        try:
            file = save_image(get(c["url"]), out / str(n))
        except (urllib.error.HTTPError, urllib.error.URLError, subprocess.CalledProcessError, ValueError) as err:
            print(f"   skipped {c['title']} ({err})", flush=True)
            continue
        kept.append({"n": n, "file": file, **{k: v for k, v in c.items() if k != "url"}})
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
    if slot["use"] == "question" and shutil.which("convert"):
        # Question photos show about 250px wide, so 800px stays sharp on any screen.
        subprocess.run(["convert", str(IMG / f"{key}{ext}"), "-resize", "800x800>", "-strip", "-quality", "80",
                        str(IMG / f"{key}{ext}")], check=True)
    photos = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    artist = re.sub(r"\s+", " ", c["artist"])[:60]
    by = f"Photo: {artist}" if artist != "Unknown" else f"Photo {c['credit']}" if c["credit"].startswith("via ") else "Photo: unknown author"
    photos[key] = {
        "src": f"photos/img/{key}{ext}", "alt": slot["alt"], "caption": caption or slot["alt"],
        "credit": by, "license": c["license"], "link": c["link"], "source": c["title"],
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
        source = "openverse" if "--openverse" in args else "commons"
        keys = [a for a in args if not a.startswith("--")]
        for s in SLOTS:
            if not keys or s["key"] in keys:
                try:
                    # Bands stretch across the page; question photos show small, so they can be smaller.
                    search(s["key"], s.get("query_" + source, s["query"]), source, 800 if s["use"] == "band" else 600)
                except urllib.error.HTTPError as err:
                    raise SystemExit(f"Wikimedia Commons refused the request ({err}). Wait a few minutes and search the remaining slots again.")
                except OSError as err:
                    raise SystemExit(f"Could not reach Wikimedia Commons ({err}). Allow commons.wikimedia.org and upload.wikimedia.org.")
    elif cmd == "pick":
        cap = args[args.index("--caption") + 1] if "--caption" in args else None
        pick(args[0], args[1], cap)
    elif cmd == "apply":
        apply()
    else:
        print(__doc__)
