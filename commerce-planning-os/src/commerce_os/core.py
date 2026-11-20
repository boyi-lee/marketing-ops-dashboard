"""Core P0 calculations. No Shopify write capability, no network, no credentials."""
from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
import hashlib, json

SCHEMA_VERSION = "1.0.0"
RULE_VERSION = "0.1.0"

class DataContractError(ValueError):
    pass

def validate_item(item: dict[str, Any]) -> dict[str, Any]:
    required = ("store_id", "variant_id", "brand", "currency", "stock_on_hand", "unit_price", "unit_cost")
    if any(item.get(k) is None or item.get(k) == "" for k in required):
        raise DataContractError("missing required item or cost field")
    if item["currency"] != "TWD":
        raise DataContractError("currency must be explicitly normalized to TWD")
    try:
        stock = int(item["stock_on_hand"])
        price, cost = Decimal(str(item["unit_price"])), Decimal(str(item["unit_cost"]))
    except (ValueError, InvalidOperation, TypeError):
        raise DataContractError("invalid stock, price or cost") from None
    if stock < 0 or price < 0 or cost < 0:
        raise DataContractError("negative amount")
    if not item.get("source_id") or not item.get("snapshot_at"):
        raise DataContractError("lineage missing")
    return item

def normalize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {}
    for item in items:
        validate_item(item)
        key = (item["store_id"], item["variant_id"])
        if key in unique:
            raise DataContractError("duplicate variant identity")
        unique[key] = item
    return list(unique.values())

def inventory_summary(items: list[dict[str, Any]], inbound: list[dict[str, Any]], cutoff: str) -> dict[str, int]:
    normalize_items(items)
    on_hand = sum(int(i["stock_on_hand"]) for i in items)
    confirmed = 0
    for order in inbound:
        if order.get("status") == "confirmed" and order.get("available_at") and order["available_at"] <= cutoff:
            if int(order.get("qty", 0)) < 0:
                raise DataContractError("negative inbound")
            confirmed += int(order["qty"])
    return {"on_hand": on_hand, "confirmed_available_by_cutoff": confirmed,
            "total_potential_supply": on_hand + confirmed}

def finance_summary(items: list[dict[str, Any]], quantities: dict[tuple[str, str], int]) -> dict[str, str]:
    normalize_items(items)
    revenue, cogs = Decimal(0), Decimal(0)
    for item in items:
        q = int(quantities.get((item["store_id"], item["variant_id"]), 0))
        if q < 0 or q > int(item["stock_on_hand"]):
            raise DataContractError("scenario exceeds existing on-hand supply")
        revenue += q * Decimal(str(item["unit_price"]))
        cogs += q * Decimal(str(item["unit_cost"]))
    return {"list_price_revenue_twd": str(revenue), "catalog_cost_twd": str(cogs),
            "illustrative_gross_profit_twd": str(revenue - cogs),
            "profit_status": "illustrative_not_full_pnl"}

def forecast_gate(observed_days: int, required_days: int, source_snapshot_id: str) -> dict[str, str]:
    if not source_snapshot_id:
        raise DataContractError("source snapshot missing")
    if observed_days < 0 or required_days <= 0:
        raise DataContractError("invalid observation period")
    return {"status": "eligible_for_backtest" if observed_days >= required_days else "blocked_insufficient_history",
            "observed_days": str(observed_days), "required_days": str(required_days),
            "snapshot_id": source_snapshot_id}

def create_campaign_draft(target: int, baseline: int, hypothetical_increment: int,
                          snapshot_id: str, hypothesis: str) -> dict[str, Any]:
    if any(v < 0 for v in (target, baseline, hypothetical_increment)):
        raise DataContractError("negative scenario amount")
    if not snapshot_id or not hypothesis.strip():
        raise DataContractError("missing snapshot or hypothesis")
    scenario = baseline + hypothetical_increment
    return {"status": "draft_unverified", "target_twd": target, "baseline_twd": baseline,
            "scenario_twd": scenario, "remaining_gap_twd": max(0, target - scenario),
            "increment_status": "assumption_not_incrementality", "hypothesis": hypothesis,
            "snapshot_id": snapshot_id, "rule_version": RULE_VERSION}

def fingerprint(records: list[dict[str, Any]]) -> str:
    canonical = json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
