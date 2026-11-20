import { router, json, error, requireAuth, db, secrets } from '@appdeploy/sdk';
import { snapshotRoutes } from './snapshot-routes.ts';

type Product = {
  id: string;
  title: string;
  vendor: string;
  productType: string;
  updatedAt: string;
  variants: {
    nodes: Array<{
      id: string;
      sku: string | null;
      price: string;
      inventoryQuantity: number | null;
      updatedAt: string;
    }>;
    pageInfo: { hasNextPage: boolean; endCursor: string | null };
  };
};
type ProductRecord = {
  id: string;
  store: string;
  productGid: string;
  title: string;
  vendor: string;
  category: string;
  updatedAt: string;
  fetchedAt: string;
  variants: Array<{
    id: string;
    sku: string | null;
    price: string;
    stock: number | null;
  }>;
};
type State = {
  id: string;
  cursor: string | null;
  synced: number;
  complete: boolean;
  updatedAt: string;
  status: string;
  sourceCount?: number;
  precision?: string;
};
const STORE = 'descente_tw';
const EXPECTED_DOMAIN = 'descente-tw.myshopify.com';
const PRIMARY_QUERY = `query ProductPage($cursor: String) {
  products(first: 30, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id title vendor productType updatedAt
      variants(first: 100) {
        pageInfo { hasNextPage endCursor }
        nodes { id sku price inventoryQuantity updatedAt }
      }
    }
  }
}`;
const VARIANT_QUERY = `query VariantPage($id: ID!, $cursor: String) {
  product(id: $id) {
    id
    variants(first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { id sku price inventoryQuantity updatedAt }
    }
  }
}`;

const COUNT_QUERY = `query SourceProductCount { productsCount(limit: null) { count precision } }`;

async function ownerAccess(email: string | undefined) {
  const names = await secrets.listSecretNames();
  if (!names.includes('COMMERCE_OWNER_EMAIL')) return false;
  const owner = (await secrets.readSecret('COMMERCE_OWNER_EMAIL'))
    .trim()
    .toLowerCase();
  return Boolean(email && owner && owner === email.toLowerCase());
}

async function connectionStatus() {
  const names = await secrets.listSecretNames();
  return {
    ownerConfigured: names.includes('COMMERCE_OWNER_EMAIL'),
    shopifyConfigured:
      names.includes('COMMERCE_SHOPIFY_CLIENT_ID') &&
      names.includes('COMMERCE_SHOPIFY_CLIENT_SECRET') &&
      names.includes('COMMERCE_SHOPIFY_DOMAIN'),
  };
}

function safeProductId(gid: string) {
  const match = /^gid:\/\/shopify\/Product\/(\d+)$/.exec(gid);
  if (!match) throw new Error('invalid_product_identifier');
  return 'product_' + match[1];
}

type CachedToken = { value: string; expiresAt: number };
let cachedShopifyToken: CachedToken | null = null;

async function getShopifyAccessToken(domain: string) {
  if (cachedShopifyToken && cachedShopifyToken.expiresAt > Date.now()) {
    return cachedShopifyToken.value;
  }
  const clientId = await secrets.readSecret('COMMERCE_SHOPIFY_CLIENT_ID');
  const clientSecret = await secrets.readSecret('COMMERCE_SHOPIFY_CLIENT_SECRET');
  if (!clientId || !clientSecret || domain !== EXPECTED_DOMAIN) {
    throw new Error('shopify_client_credentials_not_configured');
  }
  const params = new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: clientId,
    client_secret: clientSecret,
  });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 18000);
  try {
    const response = await fetch(
      'https://' + EXPECTED_DOMAIN + '/admin/oauth/access_token',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: params.toString(),
        signal: controller.signal,
      }
    );
    if (!response.ok) throw new Error('shopify_oauth_exchange_failed');
    const data = await response.json() as {
      access_token?: string;
      expires_in?: number;
      scope?: string;
    };
    const granted = (data.scope || '').split(',').map(value => value.trim());
    if (!data.access_token || typeof data.expires_in !== 'number' ||
        data.expires_in <= 90 || !granted.includes('read_products') ||
        !granted.includes('read_inventory') ||
        granted.some(scope => scope.startsWith('write_'))) {
      throw new Error('shopify_scope_or_expiry_invalid');
    }
    cachedShopifyToken = {
      value: data.access_token,
      expiresAt: Date.now() + (data.expires_in - 90) * 1000,
    };
    return cachedShopifyToken.value;
  } finally {
    clearTimeout(timeout);
  }
}

async function shopifyQuery(query: string, variables: Record<string, unknown>) {
  const domain = (await secrets.readSecret('COMMERCE_SHOPIFY_DOMAIN'))
    .trim()
    .toLowerCase();
  if (domain !== EXPECTED_DOMAIN)
    throw new Error('invalid_shopify_domain');
  const token = await getShopifyAccessToken(domain);
  const url = 'https://' + domain + '/admin/api/2026-10/graphql.json';
  let lastError = '';
  for (let i = 0; i < 3; i++) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 18000);
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Shopify-Access-Token': token,
        },
        body: JSON.stringify({ query, variables }),
        signal: controller.signal,
      });
      if (response.status === 401 || response.status === 403)
        throw new Error('shopify_access_denied');
      if ((response.status === 429 || response.status >= 500) && i < 2) {
        lastError = 'shopify_temporarily_unavailable';
        continue;
      }
      if (!response.ok) throw new Error('shopify_http_error');
      const payload = (await response.json()) as {
        data?: Record<string, unknown>;
        errors?: unknown[];
      };
      if (payload.errors?.length || !payload.data)
        throw new Error('shopify_query_error');
      return payload.data;
    } catch (caught) {
      const message =
        caught instanceof Error ? caught.message : 'request_failed';
      if (
        message === 'shopify_access_denied' ||
        message === 'invalid_shopify_domain' ||
        message === 'shopify_query_error'
      )
        throw new Error(message);
      lastError = 'shopify_request_failed';
    } finally {
      clearTimeout(timeout);
    }
  }
  throw new Error(lastError || 'shopify_request_failed');
}

async function completeVariants(product: Product) {
  const initial = product.variants.nodes || [];
  const all = [...initial];
  const seen = new Set(all.map(v => v.id));
  let cursor = product.variants.pageInfo.endCursor;
  let hasNext = product.variants.pageInfo.hasNextPage;
  const cursors = new Set<string>();
  for (let page = 0; hasNext && page < 20; page++) {
    if (!cursor || cursors.has(cursor))
      throw new Error('variant_pagination_invalid');
    cursors.add(cursor);
    const data = await shopifyQuery(VARIANT_QUERY, { id: product.id, cursor });
    const resolved = data.product as Product | null;
    if (!resolved || resolved.id !== product.id)
      throw new Error('variant_product_mismatch');
    for (const variant of resolved.variants.nodes) {
      if (!variant.id || seen.has(variant.id))
        throw new Error('duplicate_variant');
      seen.add(variant.id);
      all.push(variant);
    }
    cursor = resolved.variants.pageInfo.endCursor;
    hasNext = resolved.variants.pageInfo.hasNextPage;
  }
  if (hasNext) throw new Error('variant_page_limit');
  return all;
}

async function initializeTables() {
  await db.add('commerce_products', [
    { id: '_schema', kind: 'metadata', store: STORE },
  ]);
  await db.add('commerce_sync', [
    {
      id: STORE,
      cursor: null,
      synced: 0,
      complete: false,
      updatedAt: '',
      status: 'not_started',
    },
  ]);
}


async function synchronizePage(reset: boolean) {
      await initializeTables();
      const [last] = await db.get<State>('commerce_sync', [STORE], {
        consistent: true,
      });
      if (last?.complete && !reset) return { alreadyComplete: true, state: last, received: 0 };
      const cursor = reset ? null : last?.cursor || null;
      try {
        const response = await shopifyQuery(PRIMARY_QUERY, { cursor });
        const page = response.products as
          | {
              nodes: Product[];
              pageInfo: { hasNextPage: boolean; endCursor: string | null };
            }
          | undefined;
        if (!page || !Array.isArray(page.nodes) || !page.pageInfo)
          throw new Error('invalid_product_page');
        if (
          page.pageInfo.hasNextPage &&
          (!page.pageInfo.endCursor || page.pageInfo.endCursor === cursor)
        )
          throw new Error('invalid_product_cursor');
        if (!page.nodes.length && page.pageInfo.hasNextPage)
          throw new Error('empty_partial_page');
        const source = await shopifyQuery(COUNT_QUERY, {});
        const count = source.productsCount as { count: number; precision: string } | undefined;
        if (!count || !Number.isInteger(count.count) || count.count < 0) throw new Error('source_count_unavailable');
        const fetchedAt = new Date().toISOString();
        const records: ProductRecord[] = [];
        for (const product of page.nodes) {
          if (!product.id || !product.updatedAt || !product.variants?.pageInfo)
            throw new Error('invalid_product');
          const variants = await completeVariants(product);
          records.push({
            id: safeProductId(product.id),
            store: STORE,
            productGid: product.id,
            title: product.title,
            vendor: product.vendor,
            category: product.productType,
            updatedAt: product.updatedAt,
            fetchedAt,
            variants: variants.map(v => ({
              id: v.id,
              sku: v.sku,
              price: v.price,
              stock: v.inventoryQuantity,
            })),
          });
        }
        const unique = new Set(records.map(r => r.id));
        if (unique.size !== records.length)
          throw new Error('duplicate_product_page');
        const state: State = {
          id: STORE,
          cursor: page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null,
          synced: (reset ? 0 : last?.synced || 0) + records.length,
          complete: !page.pageInfo.hasNextPage,
          updatedAt: fetchedAt,
          status: !page.pageInfo.hasNextPage ?
            (count.precision === 'EXACT' && (reset ? 0 : last?.synced || 0) + records.length === count.count ? 'source_count_matched_pending_audit' : 'source_count_mismatch') : 'partial_sync',
          sourceCount: count.count,
          precision: count.precision,
        };
        // One bounded page of 30 products and checkpoint commit together.
        const updates = [
          db.tx.update(
            'commerce_products',
            records.map(record => ({ id: record.id, record }))
          ),
          db.tx.update('commerce_sync', [{ id: STORE, record: state, if: { cursor: last?.cursor || null } }]),
        ];
        await db.transact(updates);
        return {
          store: STORE,
          received: records.length,
          state,
          reconciliation: state.status,
        };
      } catch {
        throw new Error('sync_page_failed');
      }
}

export const handler = router({
  ...snapshotRoutes(ownerAccess),
  'GET /api/status': [
    requireAuth(),
    async ctx => {
      const allowed = await ownerAccess(ctx.user!.email);
      const configured = await connectionStatus();
      if (!allowed) return json({ authorized: false, configured, state: null });
      const [state] = await db.get<State>('commerce_sync', [STORE], {
        consistent: true,
      });
      return json({ authorized: true, configured, state: state || null });
    },
  ],
  'GET /api/products': [
    requireAuth(),
    async ctx => {
      if (!(await ownerAccess(ctx.user!.email)))
        return error('Access denied', 403);
      const rows = await db.list<ProductRecord>('commerce_products', {
        limit: 60,
        nextToken: ctx.query.nextToken || undefined,
      });
      const values = rows.items
        .filter(p => p.id !== '_schema' && p.store === STORE)
        .slice(0, 60);
      return json({
        store: STORE,
        products: values,
        nextToken: rows.nextToken || null,
        hasMoreInView: Boolean(rows.nextToken),
        status: 'partial_catalog_until_reconciled',
      });
    },
  ],
  'POST /api/sync': [
    requireAuth(),
    async ctx => {
      if (!(await ownerAccess(ctx.user!.email)))
        return error('Access denied', 403);
      const configured = await connectionStatus();
      if (!configured.shopifyConfigured)
        return error('Shopify read-only connection not configured', 409);
      try {
        return json(await synchronizePage((ctx.body as { reset?: boolean } | null)?.reset === true));
      } catch {
        return error('Sync rejected or unavailable; checkpoint unchanged', 502);
      }
    },
  ],
});


/** Background worker: one bounded page per run, no effect until all secure settings exist. */
export async function commerceSyncCron() {
  const configured = await connectionStatus();
  if (!configured.ownerConfigured || !configured.shopifyConfigured) {
    return { statusCode: 200 };
  }
  try {
    await synchronizePage(false);
  } catch {
    // Preserve the checkpoint and expose a sanitized scheduler failure.
    // No secrets, tokens, source data or Shopify response bodies are logged.
    throw new Error('commerce_sync_failed_checkpoint_preserved');
  }
  return { statusCode: 200 };
}
