import { useEffect, useState } from 'react';
import { api } from '@appdeploy/client';

type Snapshot = { snapshotId:string; capturedAt:string; products:number; variants:number; stock:number; missingSku:number; nextPage:number; pageCount:number; completed:boolean; updatedAt:string };
type Row = { id:string; title:string; vendor:string; status:string; variants:{id:string;sku:string|null;price:string;stock:number|null}[] };
export default function McpSnapshot() {
  const [active,setActive]=useState<Snapshot|null>(null);
  const [rows,setRows]=useState<Row[]>([]);
  const [file,setFile]=useState<File|null>(null);
  const [next,setNext]=useState<number|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [progress,setProgress]=useState('');
  const page=async (index:number,expectedId:string)=>{
    const r=await api.get('/api/mcp/products',{params:{page:index}});
    if (r.data.snapshotId!==expectedId) throw new Error('snapshot_changed');
    setRows(r.data.products);setNext(r.data.nextPage);
  };
  const refresh=async()=>{
    const r=await api.get('/api/mcp/status');const current=r.data.active as Snapshot|null;
    setActive(current);setRows([]);setNext(null);if(current) await page(0,current.snapshotId);
  };
  useEffect(()=>{void refresh().catch(()=>setMessage('無法載入 MCP 快照，請稍後重試。'));},[]);
  const submit=async()=>{
    if(!file || busy)return;
    setBusy(true);setMessage('');setProgress('檢查快照檔案…');
    try {
      if(file.size>30*1024*1024)throw new Error('file_too_large');
      const data=JSON.parse(await file.text());
      if(!data.manifest || !Array.isArray(data.pages) || data.pages.length!==data.manifest.pageCount)throw new Error('bad_file');
      const result=await api.post('/api/mcp/start',data.manifest);let state=result.data as Snapshot;
      if(!state.completed){
        // Reconcile every page receipt on retry; do not silently accept a changed file.
        for(let i=0;i<data.pages.length;i++){
          setProgress(`驗證／匯入批次 ${i+1} / ${data.pages.length}`);
          const r=await api.post('/api/mcp/page',{snapshotId:data.manifest.snapshotId,index:i,products:data.pages[i]});state=r.data as Snapshot;
        }
      }
      await api.post('/api/mcp/finish',{snapshotId:data.manifest.snapshotId});await refresh();
      setMessage('快照匯入完成，筆數與上傳清單一致。');
    } catch {setMessage('匯入未完成或檔案不正確。原本版本不變；可重新選擇同一檔案續傳。');}
    finally{setBusy(false);setProgress('');}
  };
  return <section className='panel'>
    <div className='paneltop'><div><h2>MCP 真實商品快照</h2><p>不需要額外 Shopify API 密鑰。資料從已授權 MCP 讀取，透過核准管理員匯入。</p></div><button className='quiet' disabled={busy} onClick={()=>void refresh().catch(()=>setMessage('重新整理失敗'))}>重新整理</button></div>
    <div className='checks'><div><span>商品 / 規格</span><strong>{active ? `${active.products} / ${active.variants}`:'尚未匯入'}</strong></div><div><span>庫存合計</span><strong>{active?.stock??'待匯入'}</strong></div><div><span>快照時間</span><strong>{active ? new Date(active.capturedAt).toLocaleString('zh-TW'):'未開始'}</strong></div></div>
    <p>只接受 Commerce OS MCP JSON 快照。完成全部批次後才顯示新版本；此為快照，並非即時同步。</p>
    <label>選擇 MCP 快照檔<input type='file' accept='.json,application/json' disabled={busy} onChange={e=>setFile(e.target.files?.[0]??null)}/></label>
    <button disabled={!file||busy} onClick={()=>void submit()}>{busy?'匯入中…':'安全匯入快照'}</button>
    {progress&&<p role='status'>{progress}</p>}{message&&<p role='status'>{message}</p>}
    {active&&<><p>已啟用版本：{active.snapshotId.slice(0,12)} · 缺 SKU：{active.missingSku} · 來源清單筆數一致（非獨立即時來源稽核）</p><div className='tablewrap'><table><thead><tr><th>商品</th><th>狀態</th><th>SKU</th><th>售價</th><th>庫存</th></tr></thead><tbody>{rows.flatMap(p=>p.variants.map(v=><tr key={v.id}><td>{p.title}<small>{p.vendor}</small></td><td>{p.status}</td><td>{v.sku||'未設定'}</td><td>{v.price}</td><td>{v.stock??'未知'}</td></tr>))}</tbody></table></div>{next!==null&&<button className='quiet' disabled={busy} onClick={()=>void page(next,active.snapshotId).catch(()=>setMessage('讀取失敗，請重新整理。'))}>下一批商品</button>}</>}
  </section>;
}
