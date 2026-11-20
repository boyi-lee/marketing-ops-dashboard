import { db, error, json, requireAuth, type RouterRoutes } from '@appdeploy/sdk';
import { parseManifest, parsePage, numericId, sha256, type Manifest, type Page } from './snapshot-contract.ts';

type State = Manifest & { nextPage: number; products: number; variants: number; stock: number; missingSku: number; lastId: string; completed: boolean; updatedAt: string };
type Receipt = { hash: string; page: Page };
type Active = { snapshotId: string };
const TABLE = 'mcp_snapshot_manifest';
const PAGES = 'mcp_snapshot_pages';
const ACTIVE = 'mcp_snapshot_active';
const key = (owner: string, id: string) => owner + '_' + id;
const pageKey = (owner: string, id: string, n: number) => key(owner,id) + '_' + n;
const validId = (id: unknown): id is string => typeof id === 'string' && /^[a-f0-9]{64}$/.test(id);
const readState = async (owner: string,id: string) => (await db.get<State>(TABLE,[key(owner,id)],{consistent:true}))[0];
const activeState = async (owner: string) => {
  const [active] = await db.get<Active>(ACTIVE,[owner],{consistent:true});
  return active ? readState(owner,active.snapshotId) : null;
};
export function snapshotRoutes(ownerAccess: (email: string | undefined)=>Promise<boolean>): RouterRoutes {
  return {
    'POST /api/mcp/start': [requireAuth(), async ctx => {
      if (!await ownerAccess(ctx.user?.email)) return error('Access denied',403);
      const owner = ctx.user!.userId;
      let m: Manifest; try { m=parseManifest(ctx.body); } catch { return error('Invalid manifest',400); }
      if (await sha256(m.pageHashes.join('')) !== m.snapshotId) return error('Manifest hash mismatch',400);
      const existing = await readState(owner,m.snapshotId);
      if (existing) {
        if (JSON.stringify(parseManifest(existing)) !== JSON.stringify(m)) return error('Manifest conflict',409);
        return json(existing);
      }
      const state: State = {...m,nextPage:0,products:0,variants:0,stock:0,missingSku:0,lastId:'',completed:false,updatedAt:new Date().toISOString()};
      await db.tx.add(TABLE,[{id:key(owner,m.snapshotId),...state}]);
      const saved=await readState(owner,m.snapshotId);
      if (!saved || JSON.stringify(parseManifest(saved)) !== JSON.stringify(m)) return error('Manifest conflict',409);
      return json(saved);
    }],
    'POST /api/mcp/page': [requireAuth(), async ctx => {
      if (!await ownerAccess(ctx.user?.email)) return error('Access denied',403);
      const owner=ctx.user!.userId;
      const b=ctx.body as {snapshotId?:unknown;index?:unknown;products?:unknown} | null;
      if (!b || !validId(b.snapshotId) || typeof b.index!=='number' || !Number.isSafeInteger(b.index) || b.index<0) return error('Invalid page envelope',400);
      let page:Page; try { page=await parsePage(b.products); } catch {return error('Invalid snapshot page',400);}
      const state=await readState(owner,b.snapshotId);
      if (!state || b.index>=state.pageCount) return error('Unknown snapshot or page',409);
      if (page.hash !== state.pageHashes[b.index]) return error('Page hash mismatch',409);
      const pk=pageKey(owner,b.snapshotId,b.index);
      if (b.index<state.nextPage) {
        const [receipt]=await db.get<Receipt>(PAGES,[pk],{consistent:true});
        return receipt?.hash===page.hash ? json(state) : error('Page replay mismatch',409);
      }
      if (state.completed || b.index!==state.nextPage || (state.lastId && numericId(page.firstId)<=numericId(state.lastId)) || state.products+page.products.length>state.productCount || state.variants+page.variantCount>state.variantCount) return error('Page sequence or count conflict',409);
      const next:State={...state,nextPage:state.nextPage+1,products:state.products+page.products.length,variants:state.variants+page.variantCount,stock:state.stock+page.stock,missingSku:state.missingSku+page.missingSku,lastId:page.lastId,updatedAt:new Date().toISOString()};
      try {
        await db.transact([db.tx.add(PAGES,[{id:pk,hash:page.hash,page}]),db.tx.update(TABLE,[{id:key(owner,b.snapshotId),record:next,if:{nextPage:state.nextPage,completed:false}}])]);
      } catch {
        // Resolve a possible committed receipt before allowing a retry.
        const [receipt]=await db.get<Receipt>(PAGES,[pk],{consistent:true});
        const saved=await readState(owner,b.snapshotId);
        if (receipt?.hash===page.hash && saved && saved.nextPage>b.index) return json(saved);
        return error('Page commit unresolved; retry same file later',409);
      }
      return json(next);
    }],
    'POST /api/mcp/finish': [requireAuth(), async ctx => {
      if (!await ownerAccess(ctx.user?.email)) return error('Access denied',403);
      const owner=ctx.user!.userId;
      const id=(ctx.body as {snapshotId?:unknown}|null)?.snapshotId;
      if (!validId(id)) return error('Invalid snapshot',400);
      const state=await readState(owner,id);
      if (!state || state.nextPage!==state.pageCount || state.products!==state.productCount || state.variants!==state.variantCount) return error('Snapshot not complete',409);
      const [active]=await db.get<Active>(ACTIVE,[owner],{consistent:true});
      if (state.completed && active?.snapshotId===id) return json(state);
      if (state.completed) return error('Older snapshot is immutable; use current active version',409);
      // Do not allow an older capture to silently replace a newer active capture.
      const previous=active ? await readState(owner,active.snapshotId) : null;
      if (previous && Date.parse(previous.capturedAt)>=Date.parse(state.capturedAt)) return error('Snapshot is not newer',409);
      const done={...state,completed:true,updatedAt:new Date().toISOString()};
      try {
        const pointer=active ? db.tx.update(ACTIVE,[{id:owner,record:{snapshotId:id},if:{snapshotId:active.snapshotId}}]) : db.tx.add(ACTIVE,[{id:owner,snapshotId:id}]);
        await db.transact([db.tx.update(TABLE,[{id:key(owner,id),record:done,if:{completed:false,nextPage:state.pageCount}}]),pointer]);
      } catch {
        const saved=await activeState(owner);
        if (saved?.completed && saved.snapshotId===id) return json(saved);
        return error('Activation unresolved; retry same file later',409);
      }
      return json(done);
    }],
    'GET /api/mcp/status': [requireAuth(), async ctx => {
      if (!await ownerAccess(ctx.user?.email)) return error('Access denied',403);
      return json({active:await activeState(ctx.user!.userId)});
    }],
    'GET /api/mcp/products': [requireAuth(), async ctx => {
      if (!await ownerAccess(ctx.user?.email)) return error('Access denied',403);
      const owner=ctx.user!.userId; const state=await activeState(owner);
      if (!state?.completed) return json({products:[],nextPage:null});
      const index=Number(ctx.query.page||'0');
      if (!Number.isSafeInteger(index)||index<0||index>=state.pageCount) return error('Invalid page',400);
      const [receipt]=await db.get<Receipt>(PAGES,[pageKey(owner,state.snapshotId,index)],{consistent:true});
      if (!receipt) return error('Snapshot page unavailable',503);
      return json({products:receipt.page.products,nextPage:index+1<state.pageCount?index+1:null,snapshotId:state.snapshotId});
    }],
  };
}
