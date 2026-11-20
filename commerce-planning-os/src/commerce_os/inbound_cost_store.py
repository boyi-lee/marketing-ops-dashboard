"""Validated finance/procurement CSV -> persistent PostgreSQL import.

Imports are store-scoped, transaction-atomic and never write to Shopify.
Costs are external accounting facts, never inferred from Shopify prices.
"""
from __future__ import annotations
import hashlib
import json
from uuid import uuid4

from .imports import parse_inbound, parse_costs

def _digest(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def import_inbound_csv(connection, *, store_id, text):
    rows=parse_inbound(text,store_id=store_id)
    with connection.transaction():
        if not connection.execute("SELECT 1 FROM commerce.stores WHERE id=%s",(store_id,)).fetchone():
            raise ValueError("unknown store")
        for row in rows:
            connection.execute(
                """INSERT INTO commerce.inbound_lines
                   (id,store_id,source_document_id,external_sku,expected_qty,
                    status,expected_available_at,source_checked_at,source_hash)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (store_id,source_document_id,external_sku)
                   DO UPDATE SET expected_qty=EXCLUDED.expected_qty,status=EXCLUDED.status,
                    expected_available_at=EXCLUDED.expected_available_at,
                    source_checked_at=EXCLUDED.source_checked_at,source_hash=EXCLUDED.source_hash
                   WHERE commerce.inbound_lines.source_checked_at<=EXCLUDED.source_checked_at""",
                (str(uuid4()),store_id,row["source_document_id"],row["external_sku"],
                 row["expected_qty"],row["status"],row["expected_available_at"],
                 row["source_checked_at"],_digest(row)))
        connection.execute(
            """INSERT INTO commerce.audit_events (store_id,action,details)
               VALUES (%s,'import_inbound',%s::jsonb)""",
            (store_id,json.dumps({"rows":len(rows),"origin":"validated_csv"})))
    return {"store_id":store_id,"validated_rows":len(rows),"status":"committed"}

def import_cost_csv(connection, *, store_id, text, currency="TWD"):
    rows=parse_costs(text,store_id=store_id,expected_currency=currency)
    with connection.transaction():
        store=connection.execute("SELECT currency FROM commerce.stores WHERE id=%s",(store_id,)).fetchone()
        if not store or store[0]!=currency:
            raise ValueError("store currency mismatch")
        for row in rows:
            connection.execute(
                """INSERT INTO commerce.cost_records
                   (id,store_id,variant_gid,source_document_id,unit_cost,
                    currency,effective_at,source_hash)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (store_id,source_document_id,variant_gid,effective_at)
                   DO UPDATE SET unit_cost=EXCLUDED.unit_cost,source_hash=EXCLUDED.source_hash""",
                (str(uuid4()),store_id,row["variant_gid"],row["source_document_id"],
                 row["unit_cost"],row["currency"],row["effective_at"],_digest(row)))
        connection.execute(
            """INSERT INTO commerce.audit_events (store_id,action,details)
               VALUES (%s,'import_cost',%s::jsonb)""",
            (store_id,json.dumps({"rows":len(rows),"origin":"validated_csv"})))
    return {"store_id":store_id,"validated_rows":len(rows),"status":"committed"}

def inbound_summary(connection, *, store_id, available_by):
    if not store_id:
        raise ValueError("store scope required")
    return connection.execute(
        """SELECT COALESCE(SUM(expected_qty),0)
           FROM commerce.inbound_lines WHERE store_id=%s AND status='confirmed'
             AND expected_available_at<=%s""",(store_id,available_by)).fetchone()[0]
