import test from 'node:test';
import assert from 'node:assert/strict';
import {pacing,finance,dedupeSku,theories} from '../engine.mjs';
test('on track',()=>assert.equal(pacing(310,150,15,31).status,'進度上'));
test('zero elapsed no projection',()=>assert.equal(pacing(100,0,0,30).projection,null));
test('contribution',()=>assert.equal(finance(1000,150,.5,.1).contribution,250));
test('not net profit',()=>assert.equal(finance(1000,150,.5,.1).isNetProfit,false));
test('shared SKU counted once',()=>assert.equal(dedupeSku([{sku:'A',inventory:5},{sku:'A',inventory:5}]).items[0].inventory,5));
test('theories available',()=>assert.ok(theories.length>=6));
