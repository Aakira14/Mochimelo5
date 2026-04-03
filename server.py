from __future__ import annotations

import json
import os
import secrets
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("MOCHIMELO_DATA_DIR", str(BASE_DIR)))
TEXT_DATA_FILE = DATA_DIR / "accounts_data.txt"
JSON_DATA_FILE = DATA_DIR / "accounts_data.json"
DEFAULT_ACCOUNTS: list[dict[str, str]] = []

# Change this secret to your own private owner password.
ADMIN_SECRET = "1111"
ADMIN_TOKENS: set[str] = set()


def ensure_data_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not JSON_DATA_FILE.exists() and not TEXT_DATA_FILE.exists():
        write_accounts(DEFAULT_ACCOUNTS)
    elif read_accounts() is None:
        write_accounts(DEFAULT_ACCOUNTS)


def read_accounts() -> list[dict[str, str]]:
    if JSON_DATA_FILE.exists():
        try:
            payload = json.loads(JSON_DATA_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, list):
            accounts = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                username = str(item.get("username", "")).strip()
                password = str(item.get("password", ""))
                banned = bool(item.get("banned", False))
                if username and password:
                    accounts.append({"username": username, "password": password, "banned": banned})
            return accounts

    if not TEXT_DATA_FILE.exists():
        return []

    accounts: list[dict[str, str]] = []
    for line in TEXT_DATA_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        values: dict[str, str] = {}
        for part in parts:
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            values[key.strip().lower()] = value.strip()
        username = values.get("username")
        password = values.get("password")
        status = values.get("status", "active").lower()
        if username and password:
            accounts.append({"username": username, "password": password, "banned": status == "banned"})
    return accounts


def write_accounts(accounts: list[dict[str, str]]) -> None:
    lines = []
    for account in accounts:
        status = "banned" if account.get("banned") else "active"
        lines.append(
            f"username: {account['username']} | password: {account['password']} | status: {status}"
        )

    text_body = "\n".join(lines)
    if text_body:
        text_body += "\n"
    TEXT_DATA_FILE.write_text(text_body, encoding="utf-8")
    JSON_DATA_FILE.write_text(json.dumps(accounts, indent=2), encoding="utf-8")


class MochimeloHandler(SimpleHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON body"}, status=400)
            return None

    def _require_admin(self) -> bool:
        token = self.headers.get("X-Admin-Token", "")
        if token not in ADMIN_TOKENS:
            self._send_json({"error": "Unauthorized"}, status=401)
            return False
        return True

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/admin/accounts":
            if not self._require_admin():
                return
            ensure_data_file()
            self._send_json({"accounts": read_accounts()})
            return

        if parsed.path.startswith("/api/"):
            self._send_json({"error": "Not found"}, status=404)
            return

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        ensure_data_file()

        if parsed.path == "/api/login":
            payload = self._read_json_body()
            if payload is None:
                return

            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
            if not username or not password:
                self._send_json({"error": "Username and password are required"}, status=400)
                return

            accounts = read_accounts()
            user = next((account for account in accounts if account["username"] == username), None)
            if not user or user["password"] != password:
                self._send_json({"error": "Invalid username or password"}, status=401)
                return
            if user.get("banned"):
                self._send_json({"error": "This account has been blocked"}, status=403)
                return

            self._send_json({"ok": True, "username": username})
            return

        if parsed.path == "/api/accounts":
            payload = self._read_json_body()
            if payload is None:
                return

            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
            if not username or not password:
                self._send_json({"error": "Username and password are required"}, status=400)
                return

            accounts = read_accounts()
            if any(account["username"] == username for account in accounts):
                self._send_json({"error": "Username already exists"}, status=409)
                return

            accounts.append({"username": username, "password": password, "banned": False})
            write_accounts(accounts)
            self._send_json({"ok": True, "username": username}, status=201)
            return

        if parsed.path == "/api/admin/login":
            payload = self._read_json_body()
            if payload is None:
                return

            secret = str(payload.get("secret", ""))
            if secret != ADMIN_SECRET:
                self._send_json({"error": "Wrong owner password"}, status=401)
                return

            token = secrets.token_hex(16)
            ADMIN_TOKENS.add(token)
            self._send_json({"ok": True, "token": token})
            return

        if parsed.path == "/api/admin/ban":
            if not self._require_admin():
                return
            payload = self._read_json_body()
            if payload is None:
                return

            username = str(payload.get("username", "")).strip()
            accounts = read_accounts()
            user = next((account for account in accounts if account["username"] == username), None)
            if not user:
                self._send_json({"error": "User not found"}, status=404)
                return
            user["banned"] = True
            write_accounts(accounts)
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/admin/delete":
            if not self._require_admin():
                return
            payload = self._read_json_body()
            if payload is None:
                return

            username = str(payload.get("username", "")).strip()
            accounts = read_accounts()
            filtered_accounts = [account for account in accounts if account["username"] != username]
            if len(filtered_accounts) == len(accounts):
                self._send_json({"error": "User not found"}, status=404)
                return
            write_accounts(filtered_accounts)
            self._send_json({"ok": True})
            return

        self._send_json({"error": "Not found"}, status=404)


def run() -> None:
    ensure_data_file()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), MochimeloHandler)
    print(f"Serving Mochimelo on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
