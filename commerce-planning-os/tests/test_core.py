import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from commerce_os.core import (normalize_items, inventory_summary, finance_summary,
                              forecast_gate, create_campaign_draft, fingerprint, DataContractError)

def sample(store="tw"):
    return {"store_id": store, "variant_id": "v1", "brand": "DEMO",
            "currency": "TWD", "stock_on_hand": 120,
            "unit_price": "5000", "unit_cost": "2800",
            "source_id": "fixture:product1", "snapshot_at": "2026-11-20T01:00:00Z"}

class ContractTests(unittest.TestCase):
    def test_valid_item(self):
        self.assertEqual(len(normalize_items([sample()])), 1)
    def test_wrong_currency_rejected(self):
        x=sample(); x["currency"]="USD"
        with self.assertRaises(DataContractError): normalize_items([x])
    def test_cost_missing_rejected(self):
        x=sample(); x.pop("unit_cost")
        with self.assertRaises(DataContractError): normalize_items([x])
    def test_store_scoped_identity(self):
        self.assertEqual(len(normalize_items([sample("tw"),sample("hk")])),2)
    def test_duplicate_identity_rejected(self):
        with self.assertRaises(DataContractError): normalize_items([sample(),sample()])
    def test_inbound_not_counted_as_onhand(self):
        result=inventory_summary([sample()], [{"status":"tentative","qty":99,"available_at":"2026-12-01"},
            {"status":"confirmed","qty":80,"available_at":"2026-12-12"}], "2026-12-31")
        self.assertEqual(result, {"on_hand":120,"confirmed_available_by_cutoff":80,"total_potential_supply":200})
    def test_future_inbound_not_yet_available(self):
        result=inventory_summary([sample()], [{"status":"confirmed","qty":80,"available_at":"2027-01-05"}],"2026-12-31")
        self.assertEqual(result["total_potential_supply"],120)
    def test_finance_cannot_exceed_stock(self):
        with self.assertRaises(DataContractError): finance_summary([sample()],{("tw","v1"):121})
    def test_finance_is_only_illustrative(self):
        result=finance_summary([sample()],{("tw","v1"):10})
        self.assertEqual(result["illustrative_gross_profit_twd"],"22000")
        self.assertEqual(result["profit_status"],"illustrative_not_full_pnl")
    def test_inadequate_history_blocks_forecast(self):
        self.assertEqual(forecast_gate(1,30,"snapshot1")["status"],"blocked_insufficient_history")
    def test_scenario_is_not_claimed_as_causal_increment(self):
        p=create_campaign_draft(650000,540000,120000,"snap1","hypothetical")
        self.assertEqual(p["scenario_twd"],660000)
        self.assertEqual(p["status"],"draft_unverified")
    def test_missing_snapshot_blocks_plan(self):
        with self.assertRaises(DataContractError): create_campaign_draft(10,5,3,"","hypothesis")
    def test_fingerprint_is_deterministic(self):
        self.assertEqual(fingerprint([sample()]),fingerprint([sample()]))

if __name__ == "__main__": unittest.main()
