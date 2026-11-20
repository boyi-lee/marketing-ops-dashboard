// Test-only isolated SDK adapter. No credentials, network, or production records.
type Row=Record<string,unknown>;
let tables=new Map<string,Map<string,Row>>();
const table=(t:Map<string,Map<string,Row>>,name:string)=>{if(!t.has(name))t.set(name,new Map());return t.get(name)!;};
type Operation={apply:(t:Map<string,Map<string,Row>>)=>unknown;then:(resolve:(v:unknown)=>void,reject:(e:unknown)=>void)=>void};
const op=(apply:Operation['apply']):Operation=>({apply,then(resolve,reject){try{resolve(apply(tables));}catch(e){reject(e);}}});
export const db={get:async(name:string,ids:string[])=>ids.map(id=>structuredClone(table(tables,name).get(id)??null)),tx:{add:(name:string,rows:Row[])=>op(t=>rows.map(r=>{const id=String(r.id);if(table(t,name).has(id))return null;table(t,name).set(id,structuredClone(r));return id;})),update:(name:string,rows:{id:string;record:Row;if?:Row}[])=>op(t=>rows.map(r=>{const old=table(t,name).get(r.id);if(r.if&&Object.entries(r.if).some(([k,v])=>old?.[k]!==v))return false;table(t,name).set(r.id,structuredClone(r.record));return true;}))},transact:async(ops:Operation[])=>{const draft=structuredClone(tables);const results=ops.map(o=>o.apply(draft));if(results.some(r=>Array.isArray(r)&&r.some(x=>x===null||x===false)))throw new Error('aborted');tables=draft;return results;}};
export const json=(data:unknown,status=200)=>({statusCode:status,body:JSON.stringify(data)});
export const error=(message:string,status=400)=>json({message},status);
export const requireAuth=()=>async(ctx:{user?:unknown})=>ctx.user?undefined:error('Authentication required',401);
