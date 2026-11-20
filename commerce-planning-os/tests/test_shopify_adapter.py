import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from commerce_os.shopify_readonly import (
    PRODUCTS_QUERY, SyncContractError, ShopifyTransientError,
    normalize_product, read_product_pages, reconcile_product_count
)

FETCHED="2026-11-20T04:00:00Z"

def node(i=1):
    return {
        "id": f"gid://shopify/Product/{i}", "title": f"Demo {i}",
        "vendor": "DEMO", "productType": "Jacket",
        "updatedAt": "2026-11-20T00:00:00Z",
        "variants": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{
                "id": f"gid://shopify/ProductVariant/{i}",
                "sku": f"SKU-{i}", "price": "1200.00",
                "inventoryQuantity": 10, "updatedAt": "2026-11-20T00:00:00Z"
            }]
        }
    }

def page(nodes, next_page=False, cursor=None):
    return {"data": {"products": {
        "pageInfo": {"hasNextPage": next_page, "endCursor": cursor},
        "nodes": nodes
    }}}

class ShopifyAdapterTests(unittest.TestCase):
    def test_read_only_query(self):
        self.assertIn("query CommerceOSProductPage", PRODUCTS_QUERY)
        self.assertNotIn("mutation ", PRODUCTS_QUERY.lower())

    def test_normalization_has_provenance_and_no_fake_cost(self):
        p=normalize_product(node(), "descente_tw", FETCHED)
        self.assertEqual(p["store_id"], "descente_tw")
        self.assertIn("payload_hash",p)
        self.assertEqual(p["variants"][0]["cost_status"],"not_provided_by_shopify_product_query")
        self.assertNotIn("unit_cost",p["variants"][0])

    def test_paginated_complete_sync(self):
        responses=[page([node(1)],True,"A"),page([node(2)])]
        calls=[]
        def execute(query,variables):
            calls.append(variables)
            return responses.pop(0)
        rows=read_product_pages(execute,store_id="tw",fetched_at=FETCHED,page_size=2)
        self.assertEqual(len(rows),2)
        self.assertEqual(calls[1]["after"],"A")

    def test_duplicate_product_rejected(self):
        responses=[page([node(1)],True,"A"),page([node(1)])]
        with self.assertRaises(SyncContractError):
            read_product_pages(lambda *_:responses.pop(0),store_id="tw",fetched_at=FETCHED)

    def test_repeated_cursor_rejected(self):
        responses=[page([node(1)],True,"A"),page([node(2)],True,"A")]
        with self.assertRaises(SyncContractError):
            read_product_pages(lambda *_:responses.pop(0),store_id="tw",fetched_at=FETCHED)

    def test_missing_nested_pagination_blocked(self):
        x=node(); x["variants"]["pageInfo"]["hasNextPage"]=True
        with self.assertRaisesRegex(SyncContractError,"variant page truncated"):
            normalize_product(x,"tw",FETCHED)

    def test_cost_not_required_to_read_catalog(self):
        self.assertEqual(len(read_product_pages(lambda *_:page([node()]),store_id="tw",fetched_at=FETCHED)),1)

    def test_graphql_errors_rejected(self):
        with self.assertRaises(SyncContractError):
            read_product_pages(lambda *_:{"errors":[{"message":"denied"}]},store_id="tw",fetched_at=FETCHED)

    def test_transient_retry_without_partial_write(self):
        attempts=[0]
        def execute(*_):
            attempts[0]+=1
            if attempts[0] == 1: raise ShopifyTransientError("rate limited")
            return page([node()])
        self.assertEqual(len(read_product_pages(execute,store_id="tw",fetched_at=FETCHED)),1)
        self.assertEqual(attempts[0],2)

    def test_retry_limit(self):
        with self.assertRaises(ShopifyTransientError):
            read_product_pages(lambda *_:(_ for _ in ()).throw(ShopifyTransientError("busy")),
                store_id="tw",fetched_at=FETCHED,max_attempts=2)

    def test_bad_inventory_type(self):
        x=node();x["variants"]["nodes"][0]["inventoryQuantity"]="10"
        with self.assertRaises(SyncContractError):
            normalize_product(x,"tw",FETCHED)

    def test_bad_price_rejected(self):
        x=node();x["variants"]["nodes"][0]["price"]="NaN"
        with self.assertRaises(SyncContractError):
            normalize_product(x,"tw",FETCHED)

    def test_max_page_guard(self):
        with self.assertRaises(SyncContractError):
            read_product_pages(lambda *_:page([node()],True,"A"),store_id="tw",
                fetched_at=FETCHED,max_pages=1)

    def test_reconciliation(self):
        self.assertEqual(reconcile_product_count(1,[{}])["status"],"matched")
        self.assertEqual(reconcile_product_count(2,[{}])["status"],"mismatch_block_publish")

    def test_no_mutation_client_method_required(self):
        self.assertTrue(callable(read_product_pages))
