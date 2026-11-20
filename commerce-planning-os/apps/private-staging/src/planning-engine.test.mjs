import test from 'node:test';import assert from 'node:assert/strict';import {plan} from './planning-engine.mjs';
const p=(id,status,stock)=>({id:'gid://shopify/Product/'+id,title:id,category:'A',status,variants:[{stock}]});
const sales={period:{days:30},rows:[['1','1000','10'],['2','1000','10'],['3','1000','10']]};
const args={days:30,demand:1,target:1000,roas:5,paidShare:.5};
test('sales velocity and stock cap, drafts excluded',()=>{const x=plan([p('1','ACTIVE',5),p('2','DRAFT',100),p('3','ACTIVE',-2)],sales,args);assert.equal(x.total,500);assert.equal(x.eligible,1);assert.equal(x.stockRisk,2);assert.equal(x.budget,100);});
test('scenario inputs change demand and budget',()=>{const x=plan([p('1','ACTIVE',100)],sales,{...args,demand:2,paidShare:1});assert.equal(x.total,2000);assert.equal(x.budget,200);});
test('no sales does not invent forecast',()=>assert.equal(plan([p('9','ACTIVE',999)],sales,args).total,0));
test('invalid inputs rejected',()=>assert.throws(()=>plan([],sales,{...args,roas:0})));
