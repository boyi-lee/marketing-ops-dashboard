"""End-to-end fixture tests against persistent adapter and API; not real Shopify."""
import sys, tempfile, os, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from commerce_os.storage import PlanningStore,API
from commerce_os.core import DataContractError

WRITER={"stores":["tw"],"scopes":["plan:write"]}
READ={"stores":["tw"],"scopes":[]}
OTHER={"stores":["hk"],"scopes":["plan:write"]}
def item(store="tw",stock=20,ts="2026-11-20T01:00:00Z"):
    return {"store_id":store,"variant_id":"v1","brand":"DEMO","currency":"TWD","stock_on_hand":stock,"unit_price":"1000","unit_cost":"600","source_id":"fixture:1","snapshot_at":ts}

class Integration(unittest.TestCase):
    def setUp(self): self.db=PlanningStore();self.api=API(self.db)
    def test_pipeline(self):
        snap=self.db.ingest_fixture(WRITER,"tw",[item()])["snapshot_id"]
        self.db.inbound(WRITER,"tw",[{"id":"po1","variant_id":"v1","qty":15,"status":"confirmed","available_at":"2026-12-01","source_id":"po:1"}])
        code,s=self.api.request("GET","/api/v1/inventory/summary",WRITER,"tw")
        self.assertEqual((code,s["potential_supply"]),(200,35))
        code,d=self.api.request("POST","/api/v1/campaign-plans",WRITER,"tw",{"target":650000,"baseline":540000,"hypothetical_increment":120000,"snapshot_id":snap,"hypothesis":"fixture only"})
        self.assertEqual((code,d["status"]),(201,"draft_unverified"))
        self.assertEqual(len(self.api.request("GET","/api/v1/campaign-plans",WRITER,"tw")[1]["plans"]),1)
    def test_repeat_sync(self):
        self.db.ingest_fixture(WRITER,"tw",[item()])
        self.db.ingest_fixture(WRITER,"tw",[item()])
        self.assertEqual(self.db.inventory(WRITER,"tw","2026-12-31")["on_hand"],20)
    def test_old_update_does_not_overwrite(self):
        self.db.ingest_fixture(WRITER,"tw",[item(stock=30,ts="2026-11-20T10:00:00Z")])
        self.db.ingest_fixture(WRITER,"tw",[item(stock=1,ts="2026-11-19T10:00:00Z")])
        self.assertEqual(self.db.inventory(WRITER,"tw","2026-12-31")["on_hand"],30)
    def test_cross_store_rejected(self):
        self.assertEqual(self.api.request("GET","/api/v1/inventory/summary",WRITER,"hk")[0],403)
    def test_reader_cannot_plan(self):
        self.assertEqual(self.api.request("POST","/api/v1/campaign-plans",READ,"tw",{})[0],403)
    def test_no_auth(self):
        self.assertEqual(self.api.request("GET","/api/v1/inventory/summary",None,"tw")[0],401)
    def test_no_shopify_writes(self):
        self.assertEqual(self.api.request("POST","/api/v1/shopify/products",WRITER,"tw",{})[0],404)
    def test_tentative_not_counted(self):
        self.db.ingest_fixture(WRITER,"tw",[item()])
        self.db.inbound(WRITER,"tw",[{"id":"po","variant_id":"v1","qty":90,"status":"tentative","available_at":"2026-12-01","source_id":"po:1"}])
        self.assertEqual(self.db.inventory(WRITER,"tw","2026-12-31")["potential_supply"],20)
    def test_future_not_counted(self):
        self.db.ingest_fixture(WRITER,"tw",[item()])
        self.db.inbound(WRITER,"tw",[{"id":"po","variant_id":"v1","qty":90,"status":"confirmed","available_at":"2027-01-01","source_id":"po:1"}])
        self.assertEqual(self.db.inventory(WRITER,"tw","2026-12-31")["potential_supply"],20)
    def test_bad_batch_atomic(self):
        broken=item();broken["currency"]="USD"
        with self.assertRaises(DataContractError):self.db.ingest_fixture(WRITER,"tw",[item(),broken])
        self.assertEqual(self.db.inventory(WRITER,"tw","2026-12-31")["on_hand"],0)
    def test_wrong_store_snapshot(self):
        self.db.ingest_fixture(WRITER,"tw",[item()])
        code,_=self.api.request("POST","/api/v1/campaign-plans",OTHER,"hk",{"target":1,"baseline":1,"hypothetical_increment":1,"snapshot_id":"invalid","hypothesis":"x"})
        self.assertEqual(code,422)
    def test_restart_persistence(self):
        h,p=tempfile.mkstemp();os.close(h)
        try:
            db=PlanningStore(p);db.ingest_fixture(WRITER,"tw",[item()]);db.db.close()
            reloaded=PlanningStore(p)
            self.assertEqual(reloaded.inventory(WRITER,"tw","2026-12-31")["on_hand"],20)
            reloaded.db.close()
        finally:os.unlink(p)
