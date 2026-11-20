"""Network boundary for read-only Shopify Admin GraphQL.

Only a fixed, reviewed catalog query is accepted. Store domains, API version and
access tokens are configured server-side. No Shopify mutation or token logging.
"""
from __future__ import annotations
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .shopify_readonly import PRODUCTS_QUERY, ShopifyTransientError, SyncContractError

MYSHOPIFY_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

class ShopifyConfigurationError(ValueError):
    pass

class ShopifyAccessError(RuntimeError):
    pass

def graphql_transport(domain, access_token, *, api_version="2026-10",
                      opener=urlopen, sleeper=time.sleep, max_http_attempts=3):
    """Build a callable suitable for read_product_pages; no HTTP writes to Shopify.

    The only accepted operation is PRODUCTS_QUERY, so arbitrary mutations cannot
    be injected by callers. Shopify Admin API uses HTTPS POST even for queries.
    """
    if not isinstance(domain, str) or not MYSHOPIFY_DOMAIN.fullmatch(domain):
        raise ShopifyConfigurationError("require canonical myshopify.com domain")
    if not isinstance(access_token, str) or not access_token.strip():
        raise ShopifyConfigurationError("access token unavailable")
    if not re.fullmatch(r"20[0-9]{2}-(01|04|07|10)", api_version):
        raise ShopifyConfigurationError("invalid API version")
    if max_http_attempts < 1 or max_http_attempts > 8:
        raise ShopifyConfigurationError("invalid retry count")
    endpoint = f"https://{domain}/admin/api/{api_version}/graphql.json"

    def execute(query, variables):
        if query != PRODUCTS_QUERY:
            raise ShopifyAccessError("operation not allowlisted")
        if not isinstance(variables, dict):
            raise ShopifyAccessError("invalid variables")
        payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        request = Request(
            endpoint, payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": access_token,
                "User-Agent": "CommercePlanningOS-ReadOnly/0.1"
            })
        for attempt in range(max_http_attempts):
            try:
                with opener(request, timeout=25) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ShopifyAccessError("response too large")
                try:
                    result = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeError):
                    raise ShopifyAccessError("invalid Shopify JSON") from None
                if not isinstance(result, dict):
                    raise ShopifyAccessError("invalid Shopify JSON object")
                if result.get("errors"):
                    raise SyncContractError("Shopify GraphQL returned errors")
                return result
            except HTTPError as error:
                if error.code in (401, 403):
                    raise ShopifyAccessError("Shopify read permission denied") from None
                if error.code not in (429, 500, 502, 503, 504):
                    raise ShopifyAccessError(f"Shopify HTTP {error.code}") from None
                transient = True
                value = error.headers.get("Retry-After") if error.headers else None
                try:
                    delay = min(30, max(0, float(value))) if value else min(8, 2 ** attempt)
                except ValueError:
                    delay = min(8, 2 ** attempt)
            except (TimeoutError, URLError):
                transient = True
                delay = min(8, 2 ** attempt)
            if attempt + 1 >= max_http_attempts:
                raise ShopifyTransientError("Shopify temporarily unavailable") from None
            sleeper(delay)
        raise ShopifyTransientError("Shopify temporarily unavailable")

    return execute
