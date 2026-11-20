import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from commerce_os.sync_worker import synchronize_products

def product_response():
    return {"data":{"products":{"pageInfo":{"hasNextPage":False,"endCursor":None},
      "nodes":[{"id":"gid://shopify/Product/1","title":"Demo","vendor":"D","productType":"Jacket",
                "updatedAt":"2026-11-20T01:00:00Z",
                "variants":{"pageInfo":{"hasNextPage":False,"endCursor":None},
                            "nodes":[{"id":"gid://shopify/ProductVariant/1","sku":"SKU-1","price":"1000",
                                      "inventoryQuantity":5,"updatedAt":"2026-11-20T01:00:00Z"}]}}]}}}

class WorkerTests(unittest.TestCase):
    @patch("commerce_os.sync_worker.ingest_product_batch")
    def test_sync_ingests_exact_complete_batch(self, ingest):
        ingest.return_value={"records_processed":1,"run_id":"run-1","state":"completed"}
        result=synchronize_products(object(),store_id="demo",execute=lambda *_:product_response(),
                                    expected_product_count=1,now="2026-11-20T03:00:00Z")
        self.assertEqual(result["records_processed"],1)
        self.assertEqual(ingest.call_args.kwargs["store_id"],"demo")
    @patch("commerce_os.sync_worker.ingest_product_batch")
    def test_mismatch_never_ingests(self, ingest):
        with self.assertRaises(ValueError):
            synchronize_products(object(),store_id="demo",execute=lambda *_:product_response(),
                                 expected_product_count=2,now="2026-11-20T03:00:00Z")
        ingest.assert_not_called()
    @patch("commerce_os.sync_worker.ingest_product_batch")
    def test_empty_catalog_requires_review(self, ingest):
        def query(*_):
            return {"data":{"products":{"nodes":[],"pageInfo":{"hasNextPage":False}}}}
        with self.assertRaises(ValueError):
            synchronize_products(object(),store_id="demo",execute=query,
                                 now="2026-11-20T03:00:00Z")
        ingest.assert_not_called()
