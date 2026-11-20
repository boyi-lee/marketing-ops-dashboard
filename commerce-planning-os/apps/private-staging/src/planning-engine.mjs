export function plan(catalog, sales, inputs) {
  const days=Number(inputs.days), demand=Number(inputs.demand), target=Number(inputs.target), roas=Number(inputs.roas), paidShare=Number(inputs.paidShare);
  if(![days,demand,target,roas,paidShare].every(Number.isFinite)||days<1||days>365||demand<0||demand>10||target<0||roas<=0||paidShare<0||paidShare>1)throw new Error('Invalid scenario');
  const byId=new Map(sales.rows.map(r=>[String(r[0]),r]));
  const result=catalog.map(p=>{
    const id=p.id.split('/').at(-1);const row=byId.get(id);const net=Number(row?.[1]??0), units=Number(row?.[2]??0);
    const available=p.variants.reduce((sum,v)=>sum+Math.max(0,Number(v.stock??0)),0);
    const skuCount=p.variants.filter(v=>v.stock>0).length;
    const realized=units>0&&net>0?net/units:0;
    const projectedDemand=units>0&&net>0?Math.floor(units*days/sales.period.days*demand):0;
    const sellable=p.status==='ACTIVE'&&realized>0?Math.min(projectedDemand,available):0;
    const contribution=sellable*realized;
    const cover=units>0?available/(units/sales.period.days):null;
    let action=p.status!=='ACTIVE'?'非啟用商品':!row?'無期間銷售證據':units<=0||net<=0?'淨銷售非正值':available<=0?'缺貨':available<projectedDemand?'補貨／限制投放':available>projectedDemand*3&&projectedDemand>0?'庫存偏高，人工促銷評估':'主推候選';
    return {id,title:p.title,category:p.category,status:p.status,net,units,available,skuCount,realized,projectedDemand,sellable,contribution,cover,action,hasSales:Boolean(row)};
  });
  const total=result.reduce((s,r)=>s+r.contribution,0), budget=target*paidShare/roas;
  const ranked=result.sort((a,b)=>b.contribution-a.contribution||b.net-a.net||a.id.localeCompare(b.id)).map(r=>({...r,illustrativeBudget:total>0?budget*r.contribution/total:0}));
  return {rows:ranked,total,budget,gap:target-total,eligible:ranked.filter(r=>r.contribution>0).length,stockRisk:ranked.filter(r=>r.status==='ACTIVE'&&r.units>0&&r.available<r.projectedDemand).length};
}
