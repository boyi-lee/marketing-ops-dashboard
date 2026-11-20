import io
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from commerce_os.internal_api import create_app

TOKEN="a-strong-internal-secret-fixture-only"

class Connection:
    def __enter__(self): return self
    def __exit__(self,*args): return False

class PrivateAPI(unittest.TestCase):
    def setUp(self):
        self.connection=Connection()
        self.app=create_app(lambda:self.connection,internal_token=TOKEN,allowed_stores={"tw"})
    def request(self,method="GET",token=TOKEN,path="/internal/v1/stores/tw/inventory"):
        result={}
        def start(status,headers):
            result["status"]=status
            result["headers"]=dict(headers)
        with __import__("unittest").mock.patch(
            "commerce_os.internal_api.inventory_rows",
            return_value=[{"variant_gid":"v1","inventory_quantity":10}]) as patched:
            pieces=self.app({
                "REQUEST_METHOD":method,
                "PATH_INFO":path,
                "HTTP_AUTHORIZATION": "Bearer "+token if token is not None else None,
            },start)
            result["body"]=json.loads(b"".join(pieces))
            result["calls"]=patched.call_count
        return result
    def test_valid_read(self):
        r=self.request()
        self.assertEqual(r["status"],"200 OK")
        self.assertEqual(r["body"]["count"],1)
        self.assertEqual(r["body"]["store_id"],"tw")
        self.assertEqual(r["calls"],1)
    def test_requires_token(self):
        r=self.request(token=None)
        self.assertEqual(r["status"],"401 Unauthorized")
        self.assertEqual(r["calls"],0)
    def test_wrong_token(self):
        r=self.request(token="wrong")
        self.assertEqual(r["status"],"401 Unauthorized")
    def test_other_store_is_forbidden(self):
        r=self.request(path="/internal/v1/stores/hk/inventory")
        self.assertEqual(r["status"],"403 Forbidden")
        self.assertEqual(r["calls"],0)
    def test_write_is_forbidden(self):
        r=self.request(method="POST")
        self.assertEqual(r["status"],"405 Method Not Allowed")
        self.assertEqual(r["calls"],0)
    def test_invalid_path(self):
        r=self.request(path="/internal/v1/stores/tw/../inventory")
        self.assertEqual(r["status"],"404 Not Found")
    def test_no_browser_cache(self):
        self.assertEqual(self.request()["headers"]["Cache-Control"],"private, no-store")
    def test_weak_secret_rejected(self):
        with self.assertRaises(ValueError):
            create_app(lambda:self.connection,internal_token="weak",allowed_stores={"tw"})
