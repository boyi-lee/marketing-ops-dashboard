export type CatalogProduct={id:string;title:string;category:string;status:string;variants:{stock:number|null}[]};
export type SalesInput={period:{days:number};rows:string[][]};
export type Scenario={days:number;demand:number;target:number;roas:number;paidShare:number};
export type DecisionRow={id:string;title:string;category:string;status:string;net:number;units:number;available:number;skuCount:number;realized:number;projectedDemand:number;sellable:number;contribution:number;cover:number|null;action:string;hasSales:boolean;illustrativeBudget:number};
export function plan(catalog:CatalogProduct[],sales:SalesInput,inputs:Scenario):{rows:DecisionRow[];total:number;budget:number;gap:number;eligible:number;stockRisk:number};
