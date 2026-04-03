# Mochimelo

Cute pixel-style web app with login, diary, photo memory, timer, and to-do features.

## Run locally

```bash
python3 server.py
```

Then open:

```text
http://127.0.0.1:8000/
```

## Deploy to GitHub Pages

GitHub Pages serves static files only, so `index.html` redirects into `MOCHIMELO.html` for the site entry point.

Note: the app can still run in static mode for the browser-side features, but server-backed account/admin syncing requires `server.py` on a real Python host.
The local account data files are intentionally ignored so plaintext usernames/passwords are not published in the repo.

## Deploy to Render

Use a Python Web Service with:

```text
Start Command: python3 server.py
```

Set a persistent disk mount and point `MOCHIMELO_DATA_DIR` at that mount path, for example:

```text
MOCHIMELO_DATA_DIR=/var/data
```

The app now binds to Render's `PORT` automatically, so no manual port override is needed.
