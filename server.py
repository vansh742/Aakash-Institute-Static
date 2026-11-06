#!/usr/bin/env python3
"""Local Aakash Institute Khamgaon website with SQLite-backed enquiries and news."""
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
import hmac
import json
import mimetypes
import os
import secrets
import sqlite3

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("AAKASH_DATA_DIR", str(ROOT / "data"))).expanduser()
DB_PATH = DATA_DIR / "branch.db"
ADMIN_PIN = os.environ.get("AAKASH_ADMIN_PIN", "")
SESSIONS = set()


def connect_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_db():
    with connect_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS admissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                student_name TEXT NOT NULL,
                parent_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                course TEXT NOT NULL,
                current_class TEXT NOT NULL,
                previous_school TEXT NOT NULL DEFAULT '',
                academic_info TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                event_date TEXT NOT NULL DEFAULT ''
            );
        """)


def clean(value, limit):
    return str(value or "").strip()[:limit]


class Handler(BaseHTTPRequestHandler):
    server_version = "KhamgaonSite/1.0"

    def send_json(self, value, status=HTTPStatus.OK, headers=None):
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for name, val in (headers or {}).items():
            self.send_header(name, val)
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 200_000:
                raise ValueError("Request is too large.")
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            raise ValueError("Please submit valid form data.")

    def has_admin_session(self):
        cookie = self.headers.get("Cookie", "")
        token = next((part.strip().split("=", 1)[1] for part in cookie.split(";") if part.strip().startswith("khamgaon_session=")), "")
        return bool(token and token in SESSIONS)

    def require_admin(self):
        if not self.has_admin_session():
            self.send_json({"error": "Please sign in as a branch administrator."}, HTTPStatus.UNAUTHORIZED)
            return False
        return True

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/news":
            with connect_db() as db:
                rows = db.execute("SELECT * FROM news ORDER BY created_at DESC, id DESC").fetchall()
            return self.send_json([dict(row) for row in rows])
        if path == "/api/admin/status":
            return self.send_json({"signed_in": self.has_admin_session()}, HTTPStatus.OK if self.has_admin_session() else HTTPStatus.UNAUTHORIZED)
        if path == "/api/admissions":
            if not self.require_admin():
                return
            with connect_db() as db:
                rows = db.execute("SELECT * FROM admissions ORDER BY created_at DESC, id DESC").fetchall()
            return self.send_json([dict(row) for row in rows])
        if path.startswith("/api/"):
            return self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = (ROOT / relative).resolve()
        if ROOT not in target.parents and target != ROOT:
            return self.send_error(HTTPStatus.FORBIDDEN)
        if target == DB_PATH or "data" in target.relative_to(ROOT).parts or not target.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = unquote(urlparse(self.path).path)
        try:
            data = self.read_json()
        except ValueError as error:
            return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        if path == "/api/admissions":
            fields = {
                "student_name": clean(data.get("student_name"), 100),
                "parent_name": clean(data.get("parent_name"), 100),
                "phone": clean(data.get("phone"), 18),
                "email": clean(data.get("email"), 150),
                "course": clean(data.get("course"), 40),
                "current_class": clean(data.get("current_class"), 40),
                "previous_school": clean(data.get("previous_school"), 120),
                "academic_info": clean(data.get("academic_info"), 160),
                "message": clean(data.get("message"), 500),
            }
            if not all(fields[key] for key in ("student_name", "parent_name", "phone", "course", "current_class")):
                return self.send_json({"error": "Please complete all required fields."}, HTTPStatus.BAD_REQUEST)
            if len(fields["phone"]) < 8:
                return self.send_json({"error": "Please enter a valid contact number."}, HTTPStatus.BAD_REQUEST)
            columns = ["created_at", *fields.keys()]
            values = [datetime.now(timezone.utc).isoformat(timespec="seconds"), *fields.values()]
            with connect_db() as db:
                cursor = db.execute(f"INSERT INTO admissions ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
                record_id = cursor.lastrowid
            return self.send_json({"saved": True, "id": record_id}, HTTPStatus.CREATED)

        if path == "/api/admin/login":
            if not ADMIN_PIN:
                return self.send_json({"error": "Admin sign-in is not configured. Set AAKASH_ADMIN_PIN and restart the server."}, HTTPStatus.SERVICE_UNAVAILABLE)
            pin = str(data.get("pin", ""))
            if not hmac.compare_digest(pin.encode(), ADMIN_PIN.encode()):
                return self.send_json({"error": "That PIN did not match."}, HTTPStatus.UNAUTHORIZED)
            token = secrets.token_urlsafe(32)
            SESSIONS.add(token)
            return self.send_json({"signed_in": True}, headers={"Set-Cookie": f"khamgaon_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800"})

        if path == "/api/admin/logout":
            cookie = self.headers.get("Cookie", "")
            token = next((part.strip().split("=", 1)[1] for part in cookie.split(";") if part.strip().startswith("khamgaon_session=")), "")
            SESSIONS.discard(token)
            return self.send_json({"signed_in": False}, headers={"Set-Cookie": "khamgaon_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})

        if path == "/api/news":
            if not self.require_admin():
                return
            category = clean(data.get("category"), 40) or "Announcement"
            title = clean(data.get("title"), 140)
            body = clean(data.get("body"), 1500)
            event_date = clean(data.get("event_date"), 10)
            if not title or not body:
                return self.send_json({"error": "Add a headline and details before publishing."}, HTTPStatus.BAD_REQUEST)
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with connect_db() as db:
                cursor = db.execute("INSERT INTO news (created_at, category, title, body, event_date) VALUES (?, ?, ?, ?, ?)", (created_at, category, title, body, event_date))
                post_id = cursor.lastrowid
            return self.send_json({"published": True, "id": post_id}, HTTPStatus.CREATED)

        return self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        path = unquote(urlparse(self.path).path)
        if not self.require_admin():
            return
        for prefix, table in (("/api/news/", "news"), ("/api/admissions/", "admissions")):
            if path.startswith(prefix):
                try:
                    record_id = int(path[len(prefix):])
                except ValueError:
                    return self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
                with connect_db() as db:
                    cursor = db.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
                if not cursor.rowcount:
                    return self.send_json({"error": "Record not found."}, HTTPStatus.NOT_FOUND)
                return self.send_json({"deleted": True})
        return self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


if __name__ == "__main__":
    initialize_db()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"Aakash Institute Khamgaon website: http://{display_host}:{port}")
    if not ADMIN_PIN:
        print("Admin is disabled. Set AAKASH_ADMIN_PIN before starting to enable the admin workspace.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
