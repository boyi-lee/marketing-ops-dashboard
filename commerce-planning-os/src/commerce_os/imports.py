"""Strict external procurement/cost import validation for the P1 pipeline.

Files arrive from authorized humans / procurement systems; this module does not
call Shopify and cannot modify Shopify inventory. Parsed batches are returned
only after complete validation.
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any

class ImportContractError(ValueError):
    pass

def _datetime_utc(value: str) -> str:
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    except (ValueError, AttributeError):
        raise ImportContractError("invalid date/time") from None
    if dt.tzinfo is None:
        raise ImportContractError("timezone required")
    return dt.astimezone(timezone.utc).isoformat()

def _read(text: str, columns: set[str], max_rows: int) -> list[dict[str,str]]:
    if not isinstance(text,str) or len(text)>4_000_000 or max_rows<1:
        raise ImportContractError("file size or row limit")
    r=csv.DictReader(StringIO(text))
    if not r.fieldnames or len(r.fieldnames)!=len(set(r.fieldnames)):
        raise ImportContractError("duplicate or missing header")
    if not columns.issubset(set(r.fieldnames)):
        raise ImportContractError("missing required columns")
    result=[]
    for row in r:
        if len(result)>=max_rows:
            raise ImportContractError("too many rows")
        if None in row or any(v is None for v in row.values()):
            raise ImportContractError("malformed csv row")
        result.append(row)
    if not result:
        raise ImportContractError("empty import")
    return result

def parse_inbound(text: str, *, store_id: str, max_rows: int=10000) -> list[dict[str,Any]]:
    cols={"store_id","source_document_id","external_sku","expected_qty","status","expected_available_at","source_checked_at"}
    seen=set()
    result=[]
    for row in _read(text,cols,max_rows):
        if not store_id or row["store_id"]!=store_id:
            raise ImportContractError("cross-store import denied")
        key=(row["source_document_id"],row["external_sku"])
        if not all(key) or key in seen:
            raise ImportContractError("missing or duplicate document/SKU")
        seen.add(key)
        try:
            qty=int(row["expected_qty"])
        except ValueError:
            raise ImportContractError("invalid expected_qty") from None
        if qty<0 or row["expected_qty"]!=str(qty):
            raise ImportContractError("invalid expected_qty")
        if row["status"] not in ("confirmed","tentative","cancelled","received"):
            raise ImportContractError("invalid inbound status")
        expected=_datetime_utc(row["expected_available_at"])
        checked=_datetime_utc(row["source_checked_at"])
        result.append({
            "store_id":store_id,"source_document_id":key[0],
            "external_sku":key[1],"expected_qty":qty,
            "status":row["status"],"expected_available_at":expected,
            "source_checked_at":checked
        })
    return result

def parse_costs(text: str, *, store_id: str, expected_currency: str="TWD", max_rows: int=10000) -> list[dict[str,str]]:
    cols={"store_id","source_document_id","variant_gid","unit_cost","currency","effective_at"}
    result=[]
    seen=set()
    for row in _read(text,cols,max_rows):
        if not store_id or row["store_id"]!=store_id:
            raise ImportContractError("cross-store cost import denied")
        if row["currency"]!=expected_currency or not row["source_document_id"] or not row["variant_gid"]:
            raise ImportContractError("currency, document or variant invalid")
        key=(row["source_document_id"],row["variant_gid"],row["effective_at"])
        if key in seen: raise ImportContractError("duplicate cost record")
        seen.add(key)
        try:
            cost=Decimal(row["unit_cost"])
        except (InvalidOperation,TypeError):
            raise ImportContractError("invalid unit cost") from None
        if not cost.is_finite() or cost<0:
            raise ImportContractError("invalid unit cost")
        result.append({
            "store_id":store_id,"source_document_id":row["source_document_id"],
            "variant_gid":row["variant_gid"],"unit_cost":str(cost),
            "currency":row["currency"],"effective_at":_datetime_utc(row["effective_at"])
        })
    return result
