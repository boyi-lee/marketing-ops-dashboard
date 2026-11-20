import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseManifest, parsePage, numericId, sha256 } from './snapshot-contract.ts';

const fixture={id:'gid://shopify/Product/10',title:'Test',vendor:'Fixture',category:'Apparel',status:'ACTIVE',updatedAt:'2026-01-01T00:00:00Z',variants:[{id:'gid://shopify/ProductVariant/1',sku:'S',price:'10.00',stock:2}]};
test('valid page and stable hash',async()=>{const a=await parsePage([fixture]);const b=await parsePage([fixture]);assert.equal(a.hash,b.hash);assert.equal(a.variantCount,1);assert.equal(a.stock,2);});
test('reject duplicate product id',async()=>assert.rejects(parsePage([fixture,fixture])));
test('reject duplicate variant id',async()=>assert.rejects(parsePage([{...fixture,variants:[fixture.variants[0],fixture.variants[0]]}])));
test('reject malformed stock',async()=>assert.rejects(parsePage([{...fixture,variants:[{...fixture.variants[0],stock:'2'}]}])));
test('reject wrong store',()=>assert.throws(()=>parseManifest({snapshotId:'a'.repeat(64),source:'shopify_mcp',domain:'different.myshopify.com',capturedAt:'2026-01-01',productCount:1,variantCount:1,pageCount:1})));
test('full private snapshot validation and count reconciliation',async()=>{const path=process.env.MCP_SNAPSHOT_TEST_FILE;if(!path)return;const data=JSON.parse(readFileSync(path,'utf8'));const m=parseManifest(data.manifest);assert.equal(await sha256(m.pageHashes.join('')),m.snapshotId);let total=0,variants=0;let last=0n;const ids=new Set<string>();for(const [i,raw] of data.pages.entries()){const page=await parsePage(raw);assert.equal(page.hash,m.pageHashes[i]);assert.ok(numericId(page.firstId)>last);last=numericId(page.lastId);total+=page.products.length;variants+=page.variantCount;for(const p of page.products)for(const v of p.variants){assert.ok(!ids.has(v.id));ids.add(v.id);}}assert.equal(total,m.productCount);assert.equal(variants,m.variantCount);assert.equal(data.pages.length,m.pageCount);});
