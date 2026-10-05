# CRUD API for HTTP testing

A small Python API for practicing requests in Postman, Burp Suite Repeater, curl, or another HTTP client. It uses only the Python standard library and stores items in SQLite.

## Run

Requires Python 3.9 or newer. From this directory:

```bash
python3 app.py
```

The API listens on `http://127.0.0.1:8000`. Data is saved in `items.db`. Use `python3 app.py --port 8080 --db /tmp/test-items.db` to change the port or database. `--host 0.0.0.0` allows connections from other devices; the API has no authentication, so use that only on a trusted network.

### Run with Docker Compose

```bash
docker compose up --build -d
curl http://127.0.0.1:8000/health
```

The container listens on port 8000 and Compose publishes it on localhost. SQLite data is kept in the `items_data` named volume, so it survives container recreation. Stop the API with `docker compose down`; this keeps the volume. To follow logs, run `docker compose logs -f api`.

## Endpoints

| Method | Path | Action | Success |
| --- | --- | --- | --- |
| GET | `/health` | Health check | 200 |
| GET | `/api/items` | List items | 200 |
| GET | `/api/items/{id}` | Read an item | 200 |
| POST | `/api/items` | Create an item | 201 |
| PUT | `/api/items/{id}` | Replace all editable fields | 200 |
| PATCH | `/api/items/{id}` | Update supplied fields | 200 |
| DELETE | `/api/items/{id}` | Delete an item | 204 |

An item has a required nonempty `name`, optional `description` (default `""`), and optional `completed` boolean (default `false`). `PUT` requires all three fields; `PATCH` requires at least one. Responses include `id`, `created_at`, and `updated_at`. Send JSON bodies with `Content-Type: application/json`. Errors use `{"error": "message"}` with status 400 (bad JSON), 404 (missing route or item), 413 (body over 1 MiB), 415 (wrong content type), or 422 (invalid fields).

## Try it with curl

```bash
curl -i http://127.0.0.1:8000/health
curl -i -X POST http://127.0.0.1:8000/api/items \
  -H 'Content-Type: application/json' \
  -d '{"name":"Try the API","description":"A sample item","completed":false}'
curl -i http://127.0.0.1:8000/api/items
curl -i -X PATCH http://127.0.0.1:8000/api/items/1 \
  -H 'Content-Type: application/json' -d '{"completed":true}'
curl -i -X DELETE http://127.0.0.1:8000/api/items/1
```

## Postman and Burp Suite

Import [`postman_collection.json`](postman_collection.json) into Postman. Run **Create item** first; its response sets the collection's `itemId` variable for the read, update, and delete requests. Change `baseUrl` if the server uses another port.

For Burp Suite, send a request to Repeater with target `127.0.0.1:8000` and edit the method, path, headers, and body. For example:

```http
POST /api/items HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{"name":"Burp test","completed":false}
```

Burp Repeater updates `Content-Length` when sending the request. Use the returned `id` in `/api/items/{id}` requests.

## Test

```bash
python3 -m unittest -v
```
