import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from app import APIHandler, ThreadingHTTPServer, __version__, initialize_db


class APITest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test.db"
        initialize_db(db_path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), APIHandler)
        self.server.db_path = db_path
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp_dir.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        request_headers = headers or {}
        if body is not None and not isinstance(body, bytes):
            body = json.dumps(body).encode()
            request_headers = {"Content-Type": "application/json", **request_headers}
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        result = response.status, dict(response.getheaders()), json.loads(raw) if raw else None
        connection.close()
        return result

    def test_crud_and_persistence(self):
        self.assertEqual(self.request("GET", "/health")[2], {"status": "ok", "version": __version__})
        self.assertEqual(self.request("GET", "/api/items")[2], {"items": []})

        status, headers, item = self.request("POST", "/api/items", {"name": "Test item"})
        self.assertEqual(status, 201)
        self.assertEqual(headers["Location"], f"/api/items/{item['id']}")
        self.assertEqual(item["completed"], False)
        self.assertEqual(item["description"], "")
        item_id = item["id"]

        self.assertEqual(self.request("GET", f"/api/items/{item_id}")[2], item)
        self.assertEqual(len(self.request("GET", "/api/items")[2]["items"]), 1)
        updated = self.request("PUT", f"/api/items/{item_id}", {
            "name": "Replacement", "description": "Full update", "completed": True
        })[2]
        self.assertEqual(updated["name"], "Replacement")
        self.assertTrue(updated["completed"])
        patched = self.request("PATCH", f"/api/items/{item_id}", {"description": "Partial update"})[2]
        self.assertEqual(patched["description"], "Partial update")
        self.assertEqual(patched["name"], "Replacement")
        self.assertEqual(patched["created_at"], item["created_at"])

        self.assertEqual(self.request("DELETE", f"/api/items/{item_id}")[0], 204)
        self.assertEqual(self.request("GET", f"/api/items/{item_id}")[0], 404)
        self.assertEqual(self.request("GET", "/api/items")[2], {"items": []})

    def test_invalid_requests(self):
        self.assertEqual(self.request("POST", "/api/items", b"{")[0], 415)
        self.assertEqual(self.request("POST", "/api/items", b"{", {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/items", None, {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/items", None)[0], 415)
        self.assertEqual(self.request("POST", "/api/items", {"name": " "})[0], 422)
        self.assertEqual(self.request("POST", "/api/items", {"name": "x", "completed": "yes"})[0], 422)
        self.assertEqual(self.request("POST", "/api/items", {"name": "x", "extra": 1})[0], 422)
        self.assertEqual(self.request("POST", "/api/items", "not an object")[0], 422)
        self.assertEqual(self.request("POST", "/api/items", b"null", {"Content-Type": "application/json"})[0], 422)
        self.assertEqual(self.request("PATCH", "/api/items/999", {})[0], 422)
        self.assertEqual(self.request("DELETE", "/api/items/999")[0], 404)
        self.assertEqual(self.request("GET", "/missing")[0], 404)


if __name__ == "__main__":
    unittest.main()
