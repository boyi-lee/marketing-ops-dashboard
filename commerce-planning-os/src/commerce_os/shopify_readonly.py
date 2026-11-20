"""Read-only Shopify GraphQL product sync adapter.

Transport is injected: this module neither holds an access token nor creates HTTP
connections. A production worker supplies a TLS client with read-only scopes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Callable, Any

PRODUCTS_QUERY = """
query CommerceOSProductPage($first: Int!, $after: String) {
  products(first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id title vendor productType updatedAt
      variants(first: 100) {
        pageInfo { hasNextPage endCursor }
        nodes { id sku price inventoryQuantity updatedAt }
      }
    }
  }
}
""".strip()

class SyncContractError(ValueError):
    pass

class ShopifyTransientError(RuntimeError):
    pass

def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise SyncContractError("missing Shopify updatedAt")
    try:
        obj = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SyncContractError("invalid source updatedAt") from None
    if obj.tzinfo is None:
        raise SyncContractError("timezone required")
    return obj.astimezone(timezone.utc).isoformat()

def normalize_product(node: dict, store_id: str, fetched_at: str) -> dict:
    if not store_id or not isinstance(node, dict):
        raise SyncContractError("missing store or product")
    if not node.get("id") or not node.get("title"):
        raise SyncContractError("missing product id/title")
    variants = node.get("variants")
    if not isinstance(variants, dict) or not isinstance(variants.get("nodes"), list):
        raise SyncContractError("missing variant page")
    if variants.get("pageInfo", {}).get("hasNextPage"):
        raise SyncContractError("variant page truncated; nested pagination required")
    parsed = []
    ids = set()
    for raw in variants["nodes"]:
        vid = raw.get("id")
        if not vid or vid in ids:
            raise SyncContractError("missing or duplicate variant ID")
        ids.add(vid)
        try:
            price = Decimal(str(raw["price"]))
        except (KeyError, TypeError, InvalidOperation):
            raise SyncContractError("invalid variant price") from None
        if not price.is_finite() or price < 0:
            raise SyncContractError("invalid variant price")
        qty = raw.get("inventoryQuantity")
        if qty is not None and (type(qty) is not int):
            raise SyncContractError("invalid inventory quantity")
        parsed.append({
            "variant_gid": vid,
            "sku": raw.get("sku") or None,
            "price": str(price),
            "inventory_quantity": qty,
            "source_updated_at": _timestamp(raw.get("updatedAt")),
            "cost_status": "not_provided_by_shopify_product_query",
        })
    body = {
        "store_id": store_id,
        "product_gid": node["id"],
        "title": node["title"],
        "vendor": node.get("vendor"),
        "product_type": node.get("productType"),
        "source_updated_at": _timestamp(node.get("updatedAt")),
        "fetched_at": _timestamp(fetched_at),
        "variants": parsed,
    }
    # Fetch time is lineage metadata, not part of the source state identity.
    # Otherwise each polling run creates duplicate snapshots for unchanged data.
    identity = {k: v for k, v in body.items() if k != "fetched_at"}
    body["payload_hash"] = sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return body

def read_product_pages(
    execute: Callable[[str, dict], dict],
    *,
    store_id: str,
    fetched_at: str,
    page_size: int = 50,
    max_pages: int = 1000,
    max_attempts: int = 3,
) -> list[dict]:
    """Return validated products only when all pages are complete.

    Caller writes as an atomic batch; this function never saves partial results.
    """
    if not 1 <= page_size <= 100 or max_pages < 1 or max_attempts < 1:
        raise ValueError("invalid sync settings")
    records = []
    cursor = None
    visited = set()
    product_ids = set()
    for _ in range(max_pages):
        variables = {"first": page_size, "after": cursor}
        for attempt in range(max_attempts):
            try:
                response = execute(PRODUCTS_QUERY, variables)
                break
            except ShopifyTransientError:
                if attempt + 1 == max_attempts:
                    raise
        if not isinstance(response, dict) or response.get("errors"):
            raise SyncContractError("GraphQL error or unexpected response")
        page = (response.get("data") or {}).get("products")
        if not isinstance(page, dict) or not isinstance(page.get("nodes"), list):
            raise SyncContractError("missing product page")
        info = page.get("pageInfo") or {}
        for node in page["nodes"]:
            item = normalize_product(node, store_id, fetched_at)
            if item["product_gid"] in product_ids:
                raise SyncContractError("duplicate product in pagination")
            product_ids.add(item["product_gid"])
            records.append(item)
        if not info.get("hasNextPage"):
            return records
        new_cursor = info.get("endCursor")
        if not new_cursor or new_cursor == cursor or new_cursor in visited:
            raise SyncContractError("invalid or repeated page cursor")
        visited.add(new_cursor)
        cursor = new_cursor
    raise SyncContractError("max pages reached; complete sync required")

def reconcile_product_count(source_count: int, normalized: list[dict]) -> dict:
    if source_count < 0:
        raise ValueError("invalid source count")
    complete = source_count == len(normalized)
    return {
        "source_count": source_count,
        "normalized_count": len(normalized),
        "status": "matched" if complete else "mismatch_block_publish",
    }
