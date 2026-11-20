import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from commerce_os.postgres_store import apply_schema,put_store
from commerce_os.inbound_cost_store import import_inbound_csv,import_cost_csv,inbound_summary
from commerce_os.imports import ImportContractError
try:
    import psycopg
except ImportError:
    psycopg=None

IN_HEAD="store_id,source_document_id,external_sku,expected_qty,status,expected_available_at,source_checked_at\n"
C_HEAD="store_id,source_document_id,variant_gid,unit_cost,currency,effective_at\n"
def incoming(qty=10,status="confirmed",checked="2026-11-20T05:00:00Z",store="tw"):
    return IN_HEAD+f"{store},PO-1,SKU-1,{qty},{status},2026-12-05T00:00:00Z,{checked}\n"
def cost(amount="600.00",store="tw"):
    return C_HEAD+f"{store},PO-1,gid://shopify/ProductVariant/200,{amount},TWD,2026-11-20T00:00:00Z\n"

@unittest.skipUnless(psycopg and os.environ.get("COMMERCE_TEST_PG_DSN"),"PostgreSQL test DSN required")
class InboundCostPGTests(unittest.TestCase):
    def setUp(self):
        self.db=psycopg.connect(os.environ["COMMERCE_TEST_PG_DSN"],autocommit=True)
        apply_schema(self.db)
        with self.db.transaction():
            self.db.execute("""TRUNCATE commerce.audit_events,commerce.plans,
                commerce.cost_records,commerce.inbound_lines,commerce.raw_snapshots,
                commerce.sync_checkpoints,commerce.sync_runs,commerce.variants,
                commerce.products,commerce.stores RESTART IDENTITY CASCADE""")
        put_store(self.db,store_id="tw",domain="fixture-tw.myshopify.com",currency="TWD")
        put_store(self.db,store_id="hk",domain="fixture-hk.myshopify.com",currency="HKD")
    def tearDown(self):self.db.close()
    def test_confirmed_inbound_persisted(self):
        x=import_inbound_csv(self.db,store_id="tw",text=incoming())
        self.assertEqual(x["status"],"committed")
        self.assertEqual(inbound_summary(self.db,store_id="tw",available_by="2026-12-31"),10)
        self.assertEqual(inbound_summary(self.db,store_id="hk",available_by="2026-12-31"),0)
    def test_tentative_stock_excluded(self):
        import_inbound_csv(self.db,store_id="tw",text=incoming(status="tentative"))
        self.assertEqual(inbound_summary(self.db,store_id="tw",available_by="2026-12-31"),0)
    def test_repeated_inbound_updates_single_source_line(self):
        import_inbound_csv(self.db,store_id="tw",text=incoming(qty=10))
        import_inbound_csv(self.db,store_id="tw",text=incoming(qty=15,checked="2026-11-20T06:00:00Z"))
        self.assertEqual(inbound_summary(self.db,store_id="tw",available_by="2026-12-31"),15)
        self.assertEqual(self.db.execute("SELECT count(*) FROM commerce.inbound_lines").fetchone()[0],1)
    def test_old_inbound_does_not_overwrite(self):
        import_inbound_csv(self.db,store_id="tw",text=incoming(qty=15,checked="2026-11-20T06:00:00Z"))
        import_inbound_csv(self.db,store_id="tw",text=incoming(qty=1,checked="2026-11-20T04:00:00Z"))
        self.assertEqual(inbound_summary(self.db,store_id="tw",available_by="2026-12-31"),15)
    def test_cost_amount_idempotent(self):
        import_cost_csv(self.db,store_id="tw",text=cost())
        import_cost_csv(self.db,store_id="tw",text=cost())
        self.assertEqual(self.db.execute("SELECT count(*) FROM commerce.cost_records").fetchone()[0],1)
    def test_corrected_cost_upserts(self):
        import_cost_csv(self.db,store_id="tw",text=cost("600"))
        import_cost_csv(self.db,store_id="tw",text=cost("650"))
        self.assertEqual(str(self.db.execute("SELECT unit_cost FROM commerce.cost_records").fetchone()[0]),"650.0000")
    def test_wrong_currency_rejected_atomically(self):
        with self.assertRaises(ValueError):
            import_cost_csv(self.db,store_id="hk",text=cost(store="hk"),currency="TWD")
        self.assertEqual(self.db.execute("SELECT count(*) FROM commerce.cost_records").fetchone()[0],0)
    def test_cross_store_source_rejected(self):
        with self.assertRaises(ImportContractError):
            import_inbound_csv(self.db,store_id="tw",text=incoming(store="hk"))
        self.assertEqual(self.db.execute("SELECT count(*) FROM commerce.inbound_lines").fetchone()[0],0)
    def test_batch_with_invalid_record_rolls_back(self):
        broken=incoming()+ "tw,PO-2,SKU-2,-4,confirmed,2026-12-05T00:00:00Z,2026-11-20T05:00:00Z\n"
        with self.assertRaises(ImportContractError):
            import_inbound_csv(self.db,store_id="tw",text=broken)
        self.assertEqual(self.db.execute("SELECT count(*) FROM commerce.inbound_lines").fetchone()[0],0)
