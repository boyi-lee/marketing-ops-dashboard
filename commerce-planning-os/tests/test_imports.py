import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from commerce_os.imports import parse_inbound, parse_costs, ImportContractError
IN_HEAD="store_id,source_document_id,external_sku,expected_qty,status,expected_available_at,source_checked_at\n"
C_HEAD="store_id,source_document_id,variant_gid,unit_cost,currency,effective_at\n"
def inbound(row="tw,PO-1,SKU-A,10,confirmed,2026-12-05T00:00:00+08:00,2026-11-20T00:00:00+08:00"):
    return IN_HEAD+row+"\n"
def cost(row="tw,PO-1,gid://shopify/ProductVariant/1,600.25,TWD,2026-11-20T00:00:00+08:00"):
    return C_HEAD+row+"\n"
class ImportValidation(unittest.TestCase):
    def test_valid_inbound(self):
        x=parse_inbound(inbound(),store_id="tw")
        self.assertEqual(x[0]["expected_qty"],10)
        self.assertTrue(x[0]["expected_available_at"].endswith("+00:00"))
    def test_reject_cross_brand_import(self):
        with self.assertRaises(ImportContractError):
            parse_inbound(inbound().replace("tw,PO-1","hk,PO-1"),store_id="tw")
    def test_tentative_not_confirmed(self):
        self.assertEqual(parse_inbound(inbound().replace("confirmed","tentative"),store_id="tw")[0]["status"],"tentative")
    def test_invalid_quantity(self):
        with self.assertRaises(ImportContractError):
            parse_inbound(inbound().replace(",10,",",-1,"),store_id="tw")
    def test_duplicate_purchase_line(self):
        record=inbound().splitlines()[1]
        with self.assertRaises(ImportContractError):
            parse_inbound(inbound()+record+"\n",store_id="tw")
    def test_missing_timezone(self):
        with self.assertRaises(ImportContractError):
            parse_inbound(inbound().replace("+08:00",""),store_id="tw")
    def test_valid_cost(self):
        self.assertEqual(parse_costs(cost(),store_id="tw")[0]["unit_cost"],"600.25")
    def test_currency_isolated(self):
        with self.assertRaises(ImportContractError):
            parse_costs(cost().replace(",TWD,",",USD,"),store_id="tw")
    def test_nan_cost_rejected(self):
        with self.assertRaises(ImportContractError):
            parse_costs(cost().replace("600.25","NaN"),store_id="tw")
    def test_duplicate_columns(self):
        with self.assertRaises(ImportContractError):
            parse_costs("store_id,store_id,source_document_id,variant_gid,unit_cost,currency,effective_at\n",store_id="tw")
    def test_malformed_csv_rejected(self):
        with self.assertRaises(ImportContractError):
            parse_costs(C_HEAD+"tw,PO-1,variant,100,TWD,2026-11-20T00:00:00Z,EXTRA\n",store_id="tw")
    def test_no_cost_rows_rejected(self):
        with self.assertRaises(ImportContractError):
            parse_costs(C_HEAD,store_id="tw")
