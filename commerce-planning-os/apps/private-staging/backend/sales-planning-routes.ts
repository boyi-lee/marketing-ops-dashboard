import { db, error, json, requireAuth, type RouterRoutes } from '@appdeploy/sdk';
export type SalesSnapshot = {period:{start:string;end:string;days:number};currency:'TWD';shop:'descente-tw.myshopify.com';rows:string[][];sourceTotals:number[]};
const date=(x:unknown):x is string=>typeof x==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(x)&&Number.isFinite(Date.parse(x));
export function parseSales(x:unknown):SalesSnapshot {
  if(!x||typeof x!=='object')throw new Error('Invalid sales snapshot');
  const b=x as Partial<SalesSnapshot>;const p=b.period;
  if(b.currency!=='TWD'||b.shop!=='descente-tw.myshopify.com'||!p||!date(p.start)||!date(p.end)||!Number.isInteger(p.days)||p.days<1||p.days>365||Math.round((Date.parse(p.end)-Date.parse(p.start))/86400000)+1!==p.days||!Array.isArray(b.rows)||b.rows.length>3000||!Array.isArray(b.sourceTotals)||b.sourceTotals.length!==4||!b.sourceTotals.every(Number.isFinite))throw new Error('Invalid sales metadata');
  const ids=new Set<string>();const sums=[0,0,0,0];
  const rows=b.rows.map(r=>{if(!Array.isArray(r)||r.length!==5||typeof r[0]!=='string'||!/^\d*$/.test(r[0])||ids.has(r[0])||!r.slice(1).every(v=>typeof v==='string'&&v.trim()!==''&&Number.isFinite(Number(v)))||!Number.isSafeInteger(Number(r[2])))throw new Error('Invalid sales row');ids.add(r[0]);r.slice(1).forEach((v,i)=>sums[i]+=Number(v));return r;});
  if(sums.some((sum,i)=>Math.abs(sum-b.sourceTotals![i])>.01)||new TextEncoder().encode(JSON.stringify(rows)).length>180000)throw new Error('Sales totals mismatch');
  return {period:p,currency:b.currency,shop:b.shop,rows,sourceTotals:b.sourceTotals};
}
export function salesPlanningRoutes(ownerAccess:(email:string|undefined)=>Promise<boolean>):RouterRoutes {
  return {
    'GET /api/planning/sales':[requireAuth(),async ctx=>{if(!await ownerAccess(ctx.user?.email))return error('Access denied',403);const [snapshot]=await db.get<SalesSnapshot>('planning_sales',[ctx.user!.userId],{consistent:true});return json({snapshot:snapshot??null});}],
    'POST /api/planning/sales':[requireAuth(),async ctx=>{if(!await ownerAccess(ctx.user?.email))return error('Access denied',403);let snapshot:SalesSnapshot;try{snapshot=parseSales(ctx.body);}catch{return error('Invalid sales snapshot or mismatch',400);}const id=ctx.user!.userId;const [previous]=await db.get<SalesSnapshot>('planning_sales',[id],{consistent:true});if(previous&&previous.period.end>snapshot.period.end)return error('Older snapshot',409);const [ok]=await db.tx.update('planning_sales',[{id,record:{...snapshot}}]);if(!ok)return error('Sales save failed',409);return json({saved:true,count:snapshot.rows.length});}]
  };
}
