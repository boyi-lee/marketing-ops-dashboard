"""Fixture-only persistent SQLite adapter and API service; never accesses Shopify."""
import json, sqlite3, hashlib
from datetime import datetime, timezone
from decimal import Decimal
from .core import validate_item, normalize_items, create_campaign_draft, DataContractError

class StoreAccessDenied(PermissionError): pass
class PlanningStore:
    def __init__(self, path=":memory:"):
        self.db=sqlite3.connect(path)
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS products(store TEXT,variant TEXT,brand TEXT,stock INTEGER,price TEXT,cost TEXT,source_updated TEXT,snapshot_id TEXT,PRIMARY KEY(store,variant));
            CREATE TABLE IF NOT EXISTS inbound(id TEXT PRIMARY KEY,store TEXT,variant TEXT,qty INTEGER,status TEXT,available_at TEXT,source_id TEXT);
            CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,store TEXT,payload TEXT);
            CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,store TEXT,snapshot_id TEXT,body TEXT);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,store TEXT,action TEXT,created_at TEXT);
        """)
    def check(self,actor,store,write=False):
        if not actor or store not in actor.get("stores",[]): raise StoreAccessDenied("store denied")
        if write and "plan:write" not in actor.get("scopes",[]): raise StoreAccessDenied("write denied")
    def ingest_fixture(self,actor,store,items):
        self.check(actor,store,True)
        normalize_items(items)
        snap=hashlib.sha256(json.dumps({"store":store,"items":items},sort_keys=True).encode()).hexdigest()
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?,?)",(snap,store,json.dumps(items)))
            for i in items:
                old=self.db.execute("SELECT source_updated FROM products WHERE store=? AND variant=?",(store,i["variant_id"])).fetchone()
                if old and old["source_updated"]>i["snapshot_at"]: continue
                self.db.execute("""INSERT INTO products VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(store,variant) DO UPDATE SET brand=excluded.brand,stock=excluded.stock,price=excluded.price,cost=excluded.cost,source_updated=excluded.source_updated,snapshot_id=excluded.snapshot_id""",
                (store,i["variant_id"],i["brand"],int(i["stock_on_hand"]),str(i["unit_price"]),str(i["unit_cost"]),i["snapshot_at"],snap))
            self._audit(store,"ingest-fixture")
        return {"snapshot_id":snap,"received":len(items)}
    def inbound(self,actor,store,lines):
        self.check(actor,store,True)
        for x in lines:
            if x.get("status") not in ("confirmed","tentative","cancelled") or type(x.get("qty"))!=int or x["qty"]<0: raise DataContractError("bad inbound")
            if not x.get("id") or not x.get("source_id"): raise DataContractError("missing inbound provenance")
            datetime.fromisoformat(x["available_at"])
        with self.db:
            for x in lines:
                self.db.execute("INSERT OR REPLACE INTO inbound VALUES (?,?,?,?,?,?,?)",(x["id"],store,x["variant_id"],x["qty"],x["status"],x["available_at"],x["source_id"]))
            self._audit(store,"import-inbound")
    def inventory(self,actor,store,cutoff):
        self.check(actor,store)
        rows=self.db.execute("SELECT * FROM products WHERE store=?",(store,)).fetchall()
        n=self.db.execute("SELECT COALESCE(SUM(qty),0) FROM inbound WHERE store=? AND status='confirmed' AND available_at<=?",(store,cutoff)).fetchone()[0]
        stock=sum(r["stock"] for r in rows)
        return {"store":store,"on_hand":stock,"confirmed_inbound":n,"potential_supply":stock+n,"snapshot_ids":list(sorted(set(r["snapshot_id"] for r in rows)))}
    def campaign(self,actor,store,body):
        self.check(actor,store,True)
        if not self.db.execute("SELECT 1 FROM snapshots WHERE id=? AND store=?",(body.get("snapshot_id"),store)).fetchone(): raise DataContractError("snapshot not owned by store")
        draft=create_campaign_draft(body["target"],body["baseline"],body["hypothetical_increment"],body["snapshot_id"],body["hypothesis"])
        pid=hashlib.sha256(json.dumps({"store":store,"draft":draft},sort_keys=True).encode()).hexdigest()[:20]
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO plans VALUES (?,?,?,?)",(pid,store,body["snapshot_id"],json.dumps(draft)))
            self._audit(store,"campaign-draft")
        return {"id":pid,**draft}
    def plans(self,actor,store):
        self.check(actor,store)
        return [json.loads(r["body"]) for r in self.db.execute("SELECT body FROM plans WHERE store=?",(store,))]
    def _audit(self,store,action):
        self.db.execute("INSERT INTO audit(store,action,created_at) VALUES(?,?,?)",(store,action,datetime.now(timezone.utc).isoformat()))

class API:
    def __init__(self,db): self.db=db
    def request(self,method,path,actor,store,body=None,cutoff="2026-12-31"):
        if not actor:return 401,{"error":"authentication_required"}
        try:
            if method=="GET" and path=="/api/v1/inventory/summary": return 200,self.db.inventory(actor,store,cutoff)
            if method=="GET" and path=="/api/v1/campaign-plans": return 200,{"plans":self.db.plans(actor,store)}
            if method=="POST" and path=="/api/v1/campaign-plans": return 201,self.db.campaign(actor,store,body or {})
            if method not in ("GET","POST"): return 405,{"error":"method_not_allowed"}
            return 404,{"error":"route_not_found"}
        except StoreAccessDenied as e:return 403,{"error":str(e)}
        except (DataContractError,KeyError,ValueError,TypeError) as e:return 422,{"error":str(e)}
