"""A small persistent CRUD API for exercising HTTP clients."""

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_DB = Path(__file__).with_name("items.db")
ITEM_PATH = re.compile(r"/api/items/([1-9][0-9]*)")
FIELDS = {"name", "description", "completed"}
MAX_BODY_BYTES = 1_048_576
INVALID_BODY = object()


def connect(db_path):
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_db(db_path):
    with connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                completed INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )


def serialize(row):
    item = dict(row)
    item["completed"] = bool(item["completed"])
    return item


def validate_item(data, method):
    if not isinstance(data, dict):
        return "Request body must be a JSON object"
    unknown = set(data) - FIELDS
    if unknown:
        return "Unknown field(s): " + ", ".join(sorted(unknown))
    if method in {"POST", "PUT"} and "name" not in data:
        return "name is required"
    if method == "PUT" and ("description" not in data or "completed" not in data):
        return "PUT requires name, description, and completed"
    if method == "PATCH" and not data:
        return "PATCH requires at least one field"
    if "name" in data and (not isinstance(data["name"], str) or not data["name"].strip()):
        return "name must be a non-empty string"
    if "description" in data and not isinstance(data["description"], str):
        return "description must be a string"
    if "completed" in data and not isinstance(data["completed"], bool):
        return "completed must be a boolean"
    return None


class APIHandler(BaseHTTPRequestHandler):
    server_version = "CRUDTestAPI/1.0"

    def respond(self, status, payload=None, *, headers=None):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        if payload is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def error(self, status, message):
        self.respond(status, {"error": message})

    def read_json(self):
        if self.headers.get_content_type() != "application/json":
            self.error(415, "Content-Type must be application/json")
            return INVALID_BODY
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.error(400, "A valid Content-Length is required")
            return INVALID_BODY
        if length < 1 or length > MAX_BODY_BYTES:
            self.error(413 if length > MAX_BODY_BYTES else 400, "Invalid request body size")
            return INVALID_BODY
        try:
            return json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.error(400, "Invalid JSON")
            return INVALID_BODY

    def route(self):
        path = urlsplit(self.path).path.rstrip("/") or "/"
        if path == "/health":
            return "health", None
        if path == "/api/items":
            return "collection", None
        match = ITEM_PATH.fullmatch(path)
        if match:
            return "item", int(match.group(1))
        return None, None

    def do_GET(self):
        route, item_id = self.route()
        if route == "health":
            self.respond(200, {"status": "ok"})
        elif route == "collection":
            with connect(self.server.db_path) as connection:
                rows = connection.execute("SELECT * FROM items ORDER BY id").fetchall()
            self.respond(200, {"items": [serialize(row) for row in rows]})
        elif route == "item":
            with connect(self.server.db_path) as connection:
                row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                self.error(404, "Item not found")
            else:
                self.respond(200, serialize(row))
        else:
            self.error(404, "Route not found")

    def do_POST(self):
        route, _ = self.route()
        if route != "collection":
            self.error(404, "Route not found")
            return
        data = self.read_json()
        if data is INVALID_BODY:
            return
        problem = validate_item(data, "POST")
        if problem:
            self.error(422, problem)
            return
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.server.db_path) as connection:
            cursor = connection.execute(
                "INSERT INTO items (name, description, completed, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (data["name"].strip(), data.get("description", ""), int(data.get("completed", False)), now, now),
            )
            row = connection.execute("SELECT * FROM items WHERE id = ?", (cursor.lastrowid,)).fetchone()
        self.respond(201, serialize(row), headers={"Location": f"/api/items/{row['id']}"})

    def update_item(self, method):
        route, item_id = self.route()
        if route != "item":
            self.error(404, "Route not found")
            return
        data = self.read_json()
        if data is INVALID_BODY:
            return
        problem = validate_item(data, method)
        if problem:
            self.error(422, problem)
            return
        with connect(self.server.db_path) as connection:
            existing = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if existing is None:
                self.error(404, "Item not found")
                return
            values = serialize(existing)
            values.update(data)
            connection.execute(
                "UPDATE items SET name = ?, description = ?, completed = ?, updated_at = ? WHERE id = ?",
                (values["name"].strip(), values["description"], int(values["completed"]),
                 datetime.now(timezone.utc).isoformat(), item_id),
            )
            row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        self.respond(200, serialize(row))

    def do_PUT(self):
        self.update_item("PUT")

    def do_PATCH(self):
        self.update_item("PATCH")

    def do_DELETE(self):
        route, item_id = self.route()
        if route != "item":
            self.error(404, "Route not found")
            return
        with connect(self.server.db_path) as connection:
            cursor = connection.execute("DELETE FROM items WHERE id = ?", (item_id,))
        if cursor.rowcount == 0:
            self.error(404, "Item not found")
        else:
            self.respond(204)


def main():
    parser = argparse.ArgumentParser(description="Run the CRUD test API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=os.environ.get("CRUD_DB_PATH", str(DEFAULT_DB)))
    args = parser.parse_args()
    initialize_db(args.db)
    server = ThreadingHTTPServer((args.host, args.port), APIHandler)
    server.db_path = args.db
    print(f"CRUD API listening at http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
