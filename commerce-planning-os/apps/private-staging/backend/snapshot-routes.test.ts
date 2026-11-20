import test from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { readFileSync } from 'node:fs';
import { parsePage, sha256 } from './snapshot-contract.ts';
registerHooks({resolve(specifier,context,next){return specifier==='@appdeploy/sdk'?{url:new URL('./mock-appdeploy.ts',import.meta.url).href,shortCircuit:true}:next(specifier,context);}});
const {snapshotRoutes}=await import('./snapshot-routes.ts');
const routes=snapshotRoutes(async email=>email==='owner@example.test');
const owner={userId:'owner-fixture',email:'owner@example.test'};
async function request(route:string,body:unknown=null,user:unknown=owner,query={}){const ctx={body,user,query};for(const fn of routes[route]){const r=await fn(ctx);if(r)return {status:r.statusCode,data:JSON.parse(r.body)};}throw new Error('no response');}
test('owner import, replay, atomic visibility and permission gate',async()=>{
  const row={id:'gid://shopify/Product/100',title:'Fixture',vendor:'Fixture',category:'Shirt',status:'ACTIVE',updatedAt:'2026-01-01',variants:[{id:'gid://shopify/ProductVariant/101',sku:'S',price:'10.00',stock:2}]};
  const h=(await parsePage([row])).hash;const id=await sha256(h);const manifest={snapshotId:id,source:'shopify_mcp',domain:'descente-tw.myshopify.com',capturedAt:'2026-01-01',productCount:1,variantCount:1,pageCount:1,pageHashes:[h]};
  assert.equal((await request('POST /api/mcp/start',manifest,null)).status,401);
  assert.equal((await request('POST /api/mcp/start',manifest,{userId:'other',email:'other@example.test'})).status,403);
  assert.equal((await request('POST /api/mcp/start',manifest)).status,200);
  assert.equal((await request('POST /api/mcp/finish',{snapshotId:id})).status,409);
  assert.equal((await request('GET /api/mcp/status')).data.active,null);
  const body={snapshotId:id,index:0,products:[row]};
  assert.equal((await request('POST /api/mcp/page',body)).status,200);
  assert.equal((await request('POST /api/mcp/page',body)).data.products,1);
  assert.equal((await request('GET /api/mcp/status')).data.active,null);
  assert.equal((await request('POST /api/mcp/finish',{snapshotId:id})).status,200);
  assert.equal((await request('POST /api/mcp/finish',{snapshotId:id})).status,200);
  assert.equal((await request('GET /api/mcp/products')).data.products.length,1);
  assert.equal((await request('GET /api/mcp/products',null,{userId:'different-owner',email:'owner@example.test'})).data.products.length,0);
});
test('real private snapshot through mocked route transaction adapter',async()=>{
  const path=process.env.MCP_SNAPSHOT_TEST_FILE;if(!path)return;
  const d=JSON.parse(readFileSync(path,'utf8'));const user={userId:'private-test',email:'owner@example.test'};
  assert.equal((await request('POST /api/mcp/start',d.manifest,user)).status,200);
  for(const [index,products] of d.pages.entries())assert.equal((await request('POST /api/mcp/page',{snapshotId:d.manifest.snapshotId,index,products},user)).status,200);
  const done=await request('POST /api/mcp/finish',{snapshotId:d.manifest.snapshotId},user);assert.equal(done.status,200);assert.equal(done.data.products,6156);assert.equal(done.data.variants,19314);assert.equal(done.data.stock,48736);
  let count=0;for(let i=0;i<d.pages.length;i++){const r=await request('GET /api/mcp/products',null,user,{page:String(i)});assert.equal(r.status,200);count+=r.data.products.length;}assert.equal(count,6156);
});
