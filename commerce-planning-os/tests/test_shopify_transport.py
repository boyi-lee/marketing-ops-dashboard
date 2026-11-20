import io
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from commerce_os.shopify_transport import (
    graphql_transport, ShopifyConfigurationError, ShopifyAccessError)
from commerce_os.shopify_readonly import (
    PRODUCTS_QUERY, ShopifyTransientError, SyncContractError)

class Response:
    def __init__(self, content):
        self.stream = io.BytesIO(content)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, count):
        return self.stream.read(count)

class TransportTests(unittest.TestCase):
    def test_allowlisted_read_query(self):
        seen=[]
        def opener(req, timeout):
            seen.append(req)
            return Response(b'{"data":{"products":{"nodes":[],"pageInfo":{"hasNextPage":false}}}}')
        fn=graphql_transport("demo.myshopify.com","fixture-secret",opener=opener)
        data=fn(PRODUCTS_QUERY,{"first":2,"after":None})
        self.assertEqual(data["data"]["products"]["nodes"],[])
        self.assertEqual(seen[0].get_method(),"POST")
        self.assertEqual(seen[0].full_url,"https://demo.myshopify.com/admin/api/2026-10/graphql.json")
        self.assertNotIn(b"fixture-secret",seen[0].data)
    def test_reject_untrusted_domain(self):
        for bad in ("localhost","demo.myshopify.com.evil.org","https://demo.myshopify.com","127.0.0.1"):
            with self.assertRaises(ShopifyConfigurationError):
                graphql_transport(bad,"fixture-secret")
    def test_reject_empty_token(self):
        with self.assertRaises(ShopifyConfigurationError):
            graphql_transport("demo.myshopify.com","")
    def test_mutation_denied(self):
        fn=graphql_transport("demo.myshopify.com","fixture-secret",opener=lambda *_:self.fail("must not request"))
        with self.assertRaises(ShopifyAccessError):
            fn("mutation { productUpdate { id } }",{})
    def test_retry_after_and_recovery(self):
        waits=[];attempts=[0]
        def opener(req,timeout):
            attempts[0]+=1
            if attempts[0]==1:
                raise HTTPError(req.full_url,429,"rate limited",{"Retry-After":"3"},None)
            return Response(b'{"data":{}}')
        fn=graphql_transport("demo.myshopify.com","fixture-secret",opener=opener,sleeper=waits.append)
        self.assertEqual(fn(PRODUCTS_QUERY,{})["data"],{})
        self.assertEqual(waits,[3.0])
    def test_auth_failure_no_retry(self):
        waits=[]
        def opener(req,timeout):
            raise HTTPError(req.full_url,403,"forbidden",{},None)
        fn=graphql_transport("demo.myshopify.com","fixture-secret",opener=opener,sleeper=waits.append)
        with self.assertRaises(ShopifyAccessError):
            fn(PRODUCTS_QUERY,{})
        self.assertEqual(waits,[])
    def test_exhausted_retry(self):
        def opener(req,timeout):
            raise URLError("timeout")
        fn=graphql_transport("demo.myshopify.com","fixture-secret",opener=opener,sleeper=lambda _:None,max_http_attempts=2)
        with self.assertRaises(ShopifyTransientError):
            fn(PRODUCTS_QUERY,{})
    def test_graphql_error_blocked(self):
        fn=graphql_transport("demo.myshopify.com","fixture-secret",opener=lambda *_:Response(b'{"errors":[{"message":"unauthorized"}]}'))
        with self.assertRaises(SyncContractError):
            fn(PRODUCTS_QUERY,{})
    def test_invalid_json_denied(self):
        fn=graphql_transport("demo.myshopify.com","fixture-secret",opener=lambda *_:Response(b'not-json'))
        with self.assertRaises(ShopifyAccessError):
            fn(PRODUCTS_QUERY,{})
