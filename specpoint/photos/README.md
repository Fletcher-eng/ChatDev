# Specpoint photos

Free, credited photos for the coloured topic bands and beside exam questions.

1. `slots.json` lists every photo slot: subject bands (`bio`, `gp`), topic bands (`bio-2`, `gp-1`, ...) and questions (by question id, like `t2q1`).
2. `python specpoint/photos/fetch_photos.py search` downloads up to four freely licensed candidates per slot from Wikimedia Commons into `candidates/` (not committed). Look at them.
3. `python specpoint/photos/fetch_photos.py pick t2q1 2 --caption "Human cheek cells stained with methylene blue"` chooses one and records its author, licence and link in `photos.json`.
4. `python specpoint/photos/fetch_photos.py apply` writes `photos.json` into the website.
5. Publish the site with each `img/<key>.jpg` as a supporting file, and run `node specpoint/obsidian/build-vault.mjs` so the vault gets the same photos in `Attachments/`.

Only public domain, CC0, CC BY and CC BY-SA photos are accepted, and every photo shows its credit. Avoid photos where children's faces can be recognised.
