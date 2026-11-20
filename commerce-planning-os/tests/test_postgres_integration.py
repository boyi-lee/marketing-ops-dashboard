"""Real PostgreSQL integration tests, required in GitHub CI with a PostgreSQL service."""
from datetime import datetime
from pathlib import Path
import os
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from commerce_os.postgres_store import apply_schema, put_store, ingest_product_batch, inventory_rows
from commerce_os.shopify_readonly import normalize_product, SyncContractError

try:
    import psycopg
except ImportError:
    psycopg=None

def product(store="tw",id=1,updated="2026-11-20T02:00:00Z",stock=10):
    node={"id":f"gid://shopify/Product/{id}","title":"Jacket",
          "productType":"Outerwear","vendor":"DEMO","updatedAt":updated,
          "variants":{"pageInfo":{"hasNextPage":False},"nodes":[
              {"id":f"gid://shopify/ProductVariant/{id}","sku":f"SKU-{id}","price":"1500.00",
               "inventoryQuantity":stock,"updatedAt":updated}]}}
    return normalize_product(node,store,"2026-11-20T04:00:00Z")

@unittest.skipUnless(psycopg and os.environ.get("COMMERCE_TEST_PG_DSN"),"PostgreSQL test DSN required")
class PostgreSQLIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn=psycopg.connect(os.environ["COMMERCE_TEST_PG_DSN"], autocommit=True)
        apply_schema(cls.conn)
    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
    def setUp(self):
        with self.conn.transaction():
            self.conn.execute("""TRUNCATE commerce.audit_events,commerce.plans,
                commerce.cost_records,commerce.inbound_lines,commerce.raw_snapshots,
                commerce.sync_checkpoints,commerce.sync_runs,commerce.variants,
                commerce.products,commerce.stores RESTART IDENTITY CASCADE""")
        put_store(self.conn,store_id="tw",domain="demo-tw.myshopify.com",currency="TWD")
        put_store(self.conn,store_id="hk",domain="demo-hk.myshopify.com",currency="HKD")
    def test_full_persistent_sync_and_query(self):
        r=ingest_product_batch(self.conn,store_id="tw",products=[product()])
        self.assertEqual(r["state"],"completed")
        rows=inventory_rows(self.conn,store_id="tw")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["inventory_quantity"],10)
        self.assertEqual(len(inventory_rows(self.conn,store_id="hk")),0)
        self.assertEqual(self.conn.execute("SELECT state FROM commerce.sync_runs").fetchone()[0],"completed")
    def test_duplicate_event_idempotency(self):
        p=product()
        ingest_product_batch(self.conn,store_id="tw",products=[p])
        ingest_product_batch(self.conn,store_id="tw",products=[p])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM commerce.raw_snapshots").fetchone()[0],1)
        self.assertEqual(len(inventory_rows(self.conn,store_id="tw")),1)
    def test_old_event_cannot_overwrite_newer(self):
        ingest_product_batch(self.conn,store_id="tw",products=[product(stock=30,updated="2026-11-20T09:00:00Z")])
        ingest_product_batch(self.conn,store_id="tw",products=[product(stock=1,updated="2026-11-19T09:00:00Z")])
        self.assertEqual(inventory_rows(self.conn,store_id="tw")[0]["inventory_quantity"],30)
    def test_store_isolation_same_shopify_variant_gid(self):
        ingest_product_batch(self.conn,store_id="tw",products=[product("tw",stock=5)])
        ingest_product_batch(self.conn,store_id="hk",products=[product("hk",stock=99)])
        self.assertEqual(inventory_rows(self.conn,store_id="tw")[0]["inventory_quantity"],5)
        self.assertEqual(inventory_rows(self.conn,store_id="hk")[0]["inventory_quantity"],99)
    def test_store_identity_injection_blocked(self):
        with self.assertRaises(SyncContractError):
            ingest_product_batch(self.conn,store_id="tw",products=[product("hk")])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM commerce.products").fetchone()[0],0)
    def test_foreign_key_failure_rolls_back_entire_batch(self):
        p=product()
        bad=product(id=2)
        bad["variants"][0]["price"]="INVALID"
        with self.assertRaises(Exception):
            ingest_product_batch(self.conn,store_id="tw",products=[p,bad])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM commerce.products").fetchone()[0],0)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM commerce.sync_runs").fetchone()[0],0)
    def test_snapshot_provenance_saved(self):
        ingest_product_batch(self.conn,store_id="tw",products=[product()])
        x=self.conn.execute("SELECT payload_hash,payload FROM commerce.raw_snapshots").fetchone()
        self.assertEqual(x[0],x[1]["payload_hash"])
