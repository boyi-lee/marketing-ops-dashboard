export type Variant = { id: string; sku: string | null; price: string; stock: number | null };
export type Product = { id: string; title: string; vendor: string; category: string; status: string; updatedAt: string; variants: Variant[] };
export type Manifest = { snapshotId: string; source: 'shopify_mcp'; domain: 'descente-tw.myshopify.com'; capturedAt: string; productCount: number; variantCount: number; pageCount: number; pageHashes: string[] };
export type Page = { products: Product[]; firstId: string; lastId: string; variantCount: number; stock: number; missingSku: number; hash: string };
const gid = (s: unknown, t: string): s is string => typeof s === 'string' && new RegExp('^gid://shopify/' + t + '/[0-9]+$').test(s);
const str = (s: unknown, max: number): s is string => typeof s === 'string' && s.length <= max;
const int = (x: unknown, min: number, max: number): x is number => Number.isSafeInteger(x) && Number(x) >= min && Number(x) <= max;
const date = (x: unknown): x is string => str(x, 50) && Number.isFinite(Date.parse(x));
const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === 'object' && !Array.isArray(x);
export const numericId = (x: string) => BigInt(x.slice(x.lastIndexOf('/') + 1));
export function parseManifest(x: unknown): Manifest {
  if (!object(x) || typeof x.snapshotId !== 'string' || !/^[a-f0-9]{64}$/.test(x.snapshotId) || x.source !== 'shopify_mcp' || x.domain !== 'descente-tw.myshopify.com' || !date(x.capturedAt) || !int(x.productCount, 1, 100000) || !int(x.variantCount, 1, 1000000) || !int(x.pageCount, 1, 2000)) throw new Error('invalid_manifest');
  if (!Array.isArray(x.pageHashes) || x.pageHashes.length !== x.pageCount || !x.pageHashes.every(h=>typeof h==='string' && /^[a-f0-9]{64}$/.test(h))) throw new Error('invalid_page_hashes');
  return { snapshotId:x.snapshotId, source:x.source, domain:x.domain, capturedAt:x.capturedAt, productCount:x.productCount, variantCount:x.variantCount, pageCount:x.pageCount, pageHashes:x.pageHashes };
}
export async function sha256(text: string) { return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(n=>n.toString(16).padStart(2,'0')).join(''); }
export async function parsePage(x: unknown): Promise<Page> {
  if (!Array.isArray(x) || !int(x.length, 1, 100)) throw new Error('invalid_page');
  const products: Product[] = []; const seen = new Set<string>(); let last = 0n; let stock = 0; let missingSku = 0;
  for (const p of x) {
    if (!object(p) || !gid(p.id,'Product') || numericId(p.id) <= last || !str(p.title,1000) || !str(p.vendor,300) || !str(p.category,300) || !str(p.status,30) || !date(p.updatedAt) || !Array.isArray(p.variants) || !int(p.variants.length,1,250)) throw new Error('invalid_product');
    last = numericId(p.id); const variants: Variant[] = [];
    for (const v of p.variants) {
      if (!object(v) || !gid(v.id,'ProductVariant') || seen.has(v.id) || !(v.sku === null || str(v.sku,300)) || typeof v.price !== 'string' || !/^\d{1,12}(\.\d{1,4})?$/.test(v.price) || !(v.stock === null || int(v.stock,-100000000,100000000))) throw new Error('invalid_variant');
      seen.add(v.id); stock += v.stock ?? 0; if (!v.sku) missingSku++;
      variants.push({id:v.id,sku:v.sku,price:v.price,stock:v.stock});
    }
    products.push({id:p.id,title:p.title,vendor:p.vendor,category:p.category,status:p.status,updatedAt:p.updatedAt,variants});
  }
  const bytes = new TextEncoder().encode(JSON.stringify(products));
  if (bytes.length > 200000) throw new Error('page_too_large');
  const hash = await sha256(JSON.stringify(products));
  return {products, firstId:products[0].id, lastId:products[products.length-1].id, variantCount:seen.size, stock, missingSku, hash};
}
