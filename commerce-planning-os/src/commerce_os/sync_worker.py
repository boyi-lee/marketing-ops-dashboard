"""One-shot product sync entrypoint for an isolated backend worker.

Never schedule this in a public frontend. Use an authorized read-only Shopify
Admin credential and a dedicated PostgreSQL writer role. This is initial
full-product sync; deletions, inventory locations and incrementals are future work.
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

from .postgres_store import ingest_product_batch
from .shopify_readonly import read_product_pages, reconcile_product_count
from .shopify_transport import graphql_transport, ShopifyConfigurationError

def synchronize_products(connection, *, store_id, execute, now=None,
                         page_size=50, expected_product_count=None):
    if not store_id:
        raise ValueError("store scope required")
    now = now or datetime.now(timezone.utc).isoformat()
    products = read_product_pages(execute, store_id=store_id,
                                  fetched_at=now, page_size=page_size)
    if expected_product_count is not None:
        check = reconcile_product_count(expected_product_count, products)
        if check["status"] != "matched":
            raise ValueError("source product count mismatch, batch not committed")
    if not products:
        raise ValueError("empty catalog requires explicit review; batch not committed")
    result = ingest_product_batch(connection, store_id=store_id, products=products)
    return {
        "store_id": store_id,
        "records_processed": result["records_processed"],
        "run_id": result["run_id"],
        "state": result["state"],
        "data_origin": "shopify_read_only"
    }

def main():
    """Requires env values from a secret manager, never stdout-log credentials."""
    needed = ("COMMERCE_STORE_ID", "COMMERCE_SHOPIFY_DOMAIN",
              "COMMERCE_SHOPIFY_READ_TOKEN", "COMMERCE_PG_DSN")
    if any(not os.environ.get(k) for k in needed):
        raise ShopifyConfigurationError("worker configuration missing")
    import psycopg
    transport = graphql_transport(os.environ["COMMERCE_SHOPIFY_DOMAIN"],
                                  os.environ["COMMERCE_SHOPIFY_READ_TOKEN"])
    with psycopg.connect(os.environ["COMMERCE_PG_DSN"], autocommit=True) as connection:
        result = synchronize_products(connection,
                    store_id=os.environ["COMMERCE_STORE_ID"], execute=transport)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
