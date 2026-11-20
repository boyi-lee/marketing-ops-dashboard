"""One-path integration: mocked Shopify HTTPS -> normalized worker -> real PostgreSQL -> protected API."""
import io
import json
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

try:
    import psycopg
except ImportError:
    psycopg=None

from commerce_os.internal_api import create_app
from commerce_os.postgres_store import apply_schema,put_store
from commerce_os.shopify_transport import graphql_transport
from commerce_os.sync_worker import synchronize_products

class Response:
    def __init__(self,value):self.bytes=io.BytesIO(json.dumps(value).encode())
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,length):return self.bytes.read(length)

def fake_shopify(_req,timeout):
    assert timeout>0
    return Response({"data":{"products":{
        "pageInfo":{"hasNextPage":False,"endCursor":None},
        "nodes":[{"id":"gid://shopify/Product/100","title":"Fixture Coat",
        "vendor":"Fixture","productType":"Outerwear","updatedAt":"2026-11-20T04:00:00Z",
        "variants":{"pageInfo":{"hasNextPage":False,"endCursor":None},
        "nodes":[{"id":"gid://shopify/ProductVariant/200","sku":"FIXTURE-200",
        "price":"3600.00","inventoryQuantity":7,
        "updatedAt":"2026-11-20T04:00:00Z"}]}}]}}})

@unittest.skipUnless(psycopg and os.environ.get("COMMERCE_TEST_PG_DSN"),
                    "requires isolated test PostgreSQL")
class FullPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.connection=psycopg.connect(os.environ["COMMERCE_TEST_PG_DSN"],autocommit=True)
        apply_schema(self.connection)
        with self.connection.transaction():
            self.connection.execute("""TRUNCATE commerce.audit_events,commerce.plans,
              commerce.cost_records,commerce.inbound_lines,commerce.raw_snapshots,
              commerce.sync_checkpoints,commerce.sync_runs,commerce.variants,
              commerce.products,commerce.stores RESTART IDENTITY CASCADE""")
        put_store(self.connection,store_id="demo",domain="fixture-shop.myshopify.com",currency="TWD")
    def tearDown(self):
        self.connection.close()
    def test_https_to_db_to_private_api(self):
        client=graphql_transport("fixture-shop.myshopify.com","not-real-token",
                                 opener=fake_shopify,sleeper=lambda _:None)
        run=synchronize_products(self.connection,store_id="demo",execute=client,
                                 now="2026-11-20T05:00:00Z",expected_product_count=1)
        self.assertEqual(run["state"],"completed")
        secret="test-internal-service-secret"
        app=create_app(
            lambda:psycopg.connect(os.environ["COMMERCE_TEST_PG_DSN"]),
            internal_token=secret,allowed_stores={"demo"})
        info={}
        def start(status,headers):info["status"]=status
        payload=b"".join(app({
            "REQUEST_METHOD":"GET","PATH_INFO":"/internal/v1/stores/demo/inventory",
            "HTTP_AUTHORIZATION":"Bearer "+secret},start))
        parsed=json.loads(payload)
        self.assertEqual(info["status"],"200 OK")
        self.assertEqual(parsed["variants"][0]["sku"],"FIXTURE-200")
        self.assertEqual(parsed["variants"][0]["inventory_quantity"],7)
        self.assertNotIn("not-real-token",payload.decode())
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM commerce.raw_snapshots").fetchone()[0],1)
    def test_duplicate_worker_runs_keep_one_source_state(self):
        client=graphql_transport("fixture-shop.myshopify.com","not-real-token",
                                 opener=fake_shopify,sleeper=lambda _:None)
        for timestamp in ("2026-11-20T05:00:00Z","2026-11-20T06:00:00Z"):
            synchronize_products(self.connection,store_id="demo",
                                 execute=client,now=timestamp,expected_product_count=1)
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM commerce.raw_snapshots").fetchone()[0],1)
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM commerce.sync_runs WHERE state='completed'").fetchone()[0],2)
