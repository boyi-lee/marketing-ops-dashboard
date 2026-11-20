"""PostgreSQL-backed, store-scoped ingestion. Used only after validation and complete pagination.

No Shopify credentials or network calls live in this module. Real data ingestion
requires a caller-authenticated worker with a read-only Shopify token.
"""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal
import json
from pathlib import Path

from .shopify_readonly import SyncContractError

MIGRATION = Path(__file__).resolve().parents[2] / "database" / "migrations" / "001_init.sql"

def apply_schema(connection):
    with connection.transaction():
        connection.execute(MIGRATION.read_text(encoding="utf-8"))

def put_store(connection, *, store_id, domain, currency):
    if not store_id or not domain or len(currency) != 3:
        raise ValueError("invalid store configuration")
    with connection.transaction():
        connection.execute(
            """INSERT INTO commerce.stores (id, domain, currency) VALUES (%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET domain=EXCLUDED.domain, currency=EXCLUDED.currency""",
            (store_id, domain, currency)
        )

def ingest_product_batch(connection, *, store_id, products, source="shopify"):
    """All-or-nothing batch; runs are not marked completed unless every record succeeds."""
    if source != "shopify" or not store_id or not isinstance(products, list):
        raise SyncContractError("invalid ingestion request")
    ids = set()
    for product in products:
        if product.get("store_id") != store_id or not product.get("payload_hash"):
            raise SyncContractError("store identity/provenance mismatch")
        if product.get("product_gid") in ids:
            raise SyncContractError("duplicate product in batch")
        ids.add(product.get("product_gid"))
        if not isinstance(product.get("variants"), list):
            raise SyncContractError("invalid variant records")
        seen = set()
        for v in product["variants"]:
            if not v.get("variant_gid") or v["variant_gid"] in seen:
                raise SyncContractError("duplicate or missing variant ID")
            seen.add(v["variant_gid"])
            if Decimal(str(v["price"])) < 0:
                raise SyncContractError("negative variant price")
    run_id = str(uuid4())
    fetched_at = datetime.now(timezone.utc)
    # This entire transaction rolls back, including the sync run, when any SQL constraint fails.
    with connection.transaction():
        store = connection.execute("SELECT 1 FROM commerce.stores WHERE id=%s",(store_id,)).fetchone()
        if not store:
            raise SyncContractError("unknown store")
        connection.execute(
            "INSERT INTO commerce.sync_runs (id,store_id,source,state) VALUES (%s,%s,%s,'running')",
            (run_id, store_id, source)
        )
        for product in products:
            snap_id = str(uuid4())
            connection.execute(
                """INSERT INTO commerce.raw_snapshots
                  (id,run_id,store_id,kind,resource_gid,source_updated_at,fetched_at,payload_hash,payload)
                  VALUES (%s,%s,%s,'product',%s,%s,%s,%s,%s::jsonb)
                  ON CONFLICT (store_id,kind,resource_gid,payload_hash) DO NOTHING""",
                (snap_id,run_id,store_id,product["product_gid"],product["source_updated_at"],
                 product.get("fetched_at") or fetched_at, product["payload_hash"],json.dumps(product))
            )
            connection.execute(
                """INSERT INTO commerce.products
                  (store_id,product_gid,title,vendor,product_type,source_updated_at)
                  VALUES (%s,%s,%s,%s,%s,%s)
                  ON CONFLICT (store_id,product_gid) DO UPDATE SET
                    title=EXCLUDED.title, vendor=EXCLUDED.vendor, product_type=EXCLUDED.product_type,
                    source_updated_at=EXCLUDED.source_updated_at, ingested_at=now()
                  WHERE commerce.products.source_updated_at <= EXCLUDED.source_updated_at""",
                (store_id,product["product_gid"],product["title"],product.get("vendor"),
                 product.get("product_type"),product["source_updated_at"])
            )
            for variant in product["variants"]:
                connection.execute(
                    """INSERT INTO commerce.variants
                      (store_id,variant_gid,product_gid,sku,price,inventory_quantity,source_updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (store_id,variant_gid) DO UPDATE SET
                      sku=EXCLUDED.sku,price=EXCLUDED.price,
                      inventory_quantity=EXCLUDED.inventory_quantity,
                      source_updated_at=EXCLUDED.source_updated_at
                    WHERE commerce.variants.source_updated_at <= EXCLUDED.source_updated_at""",
                    (store_id,variant["variant_gid"],product["product_gid"],variant.get("sku"),
                     variant["price"],variant.get("inventory_quantity"),variant["source_updated_at"])
                )
        connection.execute(
            """UPDATE commerce.sync_runs SET state='completed',completed_at=now(),
               records_processed=%s WHERE id=%s""",(len(products),run_id)
        )
    return {"run_id":run_id,"records_processed":len(products),"state":"completed"}

def inventory_rows(connection, *, store_id):
    if not store_id:
        raise ValueError("store scope required")
    rows = connection.execute(
        """SELECT p.product_gid,p.title,v.variant_gid,v.sku,v.price,v.inventory_quantity,
                  v.source_updated_at
             FROM commerce.variants v
             JOIN commerce.products p ON p.store_id=v.store_id AND p.product_gid=v.product_gid
             WHERE v.store_id=%s ORDER BY p.product_gid,v.variant_gid""",
        (store_id,)
    ).fetchall()
    return [dict(zip(("product_gid","title","variant_gid","sku","price","inventory_quantity","source_updated_at"),r)) for r in rows]
