"""Private read-only WSGI API, designed for a protected backend-to-backend gateway.

Never expose this service directly to browsers or the public internet. An
authenticated BFF with OIDC/RBAC must mediate end-user sessions. This service
also requires an internal bearer token and a strict store allowlist.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from hmac import compare_digest
import json
import os
import re

from .postgres_store import inventory_rows

ROUTE = re.compile(r"^/internal/v1/stores/([a-zA-Z0-9_-]{1,64})/inventory$")

def _json_response(start_response, status, value):
    payload = json.dumps(value, ensure_ascii=False, default=_serialize).encode("utf-8")
    start_response(status, [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(payload))),
        ("Cache-Control", "private, no-store"),
        ("X-Content-Type-Options", "nosniff"),
    ])
    return [payload]

def _serialize(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError("unserializable response data")

def create_app(connection_factory, *, internal_token, allowed_stores):
    if not internal_token or len(internal_token) < 16:
        raise ValueError("strong internal bearer token required")
    allowed = frozenset(allowed_stores)
    if not allowed:
        raise ValueError("store allowlist required")

    def application(environ, start_response):
        if environ.get("REQUEST_METHOD") != "GET":
            return _json_response(start_response,"405 Method Not Allowed",{"error":"method_not_allowed"})
        if not isinstance(environ.get("HTTP_AUTHORIZATION"),str):
            return _json_response(start_response,"401 Unauthorized",{"error":"auth_required"})
        auth = environ["HTTP_AUTHORIZATION"]
        prefix = "Bearer "
        if not auth.startswith(prefix) or not compare_digest(auth[len(prefix):],internal_token):
            return _json_response(start_response,"401 Unauthorized",{"error":"auth_required"})
        path = environ.get("PATH_INFO","")
        match = ROUTE.fullmatch(path)
        if not match:
            return _json_response(start_response,"404 Not Found",{"error":"route_not_found"})
        store = match.group(1)
        if store not in allowed:
            return _json_response(start_response,"403 Forbidden",{"error":"store_denied"})
        with connection_factory() as connection:
            rows = inventory_rows(connection,store_id=store)
        return _json_response(start_response,"200 OK",{
            "store_id":store,
            "data_status":"source_snapshot_not_live_guarantee",
            "count":len(rows),
            "variants":rows,
        })
    return application

def main():
    # Bound to loopback: a trusted gateway provides TLS, OIDC, permissions
    # and maps users to a store before forwarding internal requests.
    token = os.environ.get("COMMERCE_INTERNAL_API_TOKEN","")
    stores = [x.strip() for x in os.environ.get("COMMERCE_ALLOWED_STORES","").split(",") if x.strip()]
    if not token or not stores or not os.environ.get("COMMERCE_PG_DSN"):
        raise ValueError("internal API environment not configured")
    import psycopg
    from wsgiref.simple_server import make_server
    def connect():
        return psycopg.connect(os.environ["COMMERCE_PG_DSN"])
    app = create_app(connect, internal_token=token, allowed_stores=stores)
    with make_server("127.0.0.1", 8080, app) as server:
        server.serve_forever()

if __name__ == "__main__":
    main()
