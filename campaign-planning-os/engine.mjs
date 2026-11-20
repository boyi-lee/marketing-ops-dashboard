export function pacing(target, actual, elapsed, total) {
  for(const [k,v] of Object.entries({target,actual,elapsed,total})){if(!Number.isFinite(v)||v<0)throw Error(k+" invalid")}
  if(total===0||elapsed>total)throw Error("Invalid period");
  const expected=target*elapsed/total;
  return {expected, gap:actual-expected, percent:expected?actual/expected:null, projection:elapsed?actual/elapsed*total:null,status:elapsed===0?"資料不足":actual>=expected*1.05?"領先":actual>=expected*.95?"進度上":"落後"};
}
export function finance(revenue, adSpend, margin, variableRate) {
  if([revenue,adSpend,margin,variableRate].some(x=>!Number.isFinite(x)||x<0))throw Error("Invalid amount");
  if(margin>1||variableRate>1)throw Error("Invalid rate");
  return {contribution:revenue*(margin-variableRate)-adSpend,wholeStoreRevenueOverAdSpend:adSpend?revenue/adSpend:null,breakEvenRoas:margin>variableRate?1/(margin-variableRate):null,isNetProfit:false};
}
export function dedupeSku(rows){
  const map=new Map(), warnings=[];
  for(const r of rows){
    if(!r.sku)throw Error("Missing SKU");
    const old=map.get(r.sku);
    if(old){old.inventory=Math.max(old.inventory,r.inventory);warnings.push("Duplicated SKU: "+r.sku)}
    else map.set(r.sku,{...r});
  }
  return {items:[...map.values()],warnings};
}
export const theories=[
  ["營收驅動樹","營收 = 訂單數 × 每單淨營收；用流量 × CVR 估計訂單須先校正口徑。"],
  ["安索夫矩陣","新舊商品 × 新舊市場。高庫存不代表新市場。"],
  ["ABC 商品分析","按 SKU 銷售貢獻分類，留意重複庫存、季節性及缺成本。"],
  ["STP / RFM","按客群需求、購買時間、頻率及消費價值決定溝通。"],
  ["貢獻毛利","扣商品成本、廣告費與變動費，未扣固定費不得稱淨利。"],
  ["增量評估","折扣訂單不一定是新增訂單，須與反事實基準比較。"]
];
