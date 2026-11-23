import test from 'node:test';
import assert from 'node:assert/strict';
import {surfaces,clearGroundRoute,landingWidth,classifyLocation} from '../shared/core/geometry.ts';
const p=(x,y)=>({longitude:x*.9144/111195,latitude:y*.9144/111195,accuracy_m:0});
const ring=(l,b,r,t)=>[[l,b],[r,b],[r,t],[l,t],[l,b]].map(([x,y])=>{const q=p(x,y);return [q.longitude,q.latitude];});
const zone=(id,surface,l,b,r,t)=>({id,surface,verified:true,source:'test',geometry:{type:'Polygon',coordinates:[ring(l,b,r,t)]}});
const ob=(x,b,t,simulation_only=false)=>({kind:'ob',source:'test',simulation_only,a:p(x,b),b:p(x,t),inside_reference:p(x-5,(b+t)/2)});
test('ground segments reject sub-yard water, bunker and OB polygons between samples',()=>{
 for(const kind of ['water','bunker','ob']){
  const h={surface_zones:[zone('f','fairway',-20,0,20,30),zone('hazard',kind,-20,14.2,20,14.4)]};
  assert.equal(clearGroundRoute(surfaces(h),p(0,10),p(0,20),h),false,kind);
 }
});
test('ground route crosses fairway/green seams but not unmapped gaps or polygon holes',()=>{
 const zones=[zone('f','fairway',-10,0,10,15),zone('g','green',-10,15,10,30)];
 let h={surface_zones:zones};assert.equal(clearGroundRoute(surfaces(h),p(0,10),p(0,20),h),true);
 h={surface_zones:[zones[0],zone('g','green',-10,15.2,10,30)]};assert.equal(clearGroundRoute(surfaces(h),p(0,10),p(0,20),h),false);
 const f=zone('f','fairway',-10,0,10,30);f.geometry.coordinates.push(ring(-1,14.2,1,14.4));h={surface_zones:[f]};
 assert.equal(clearGroundRoute(surfaces(h),p(0,10),p(0,20),h),false);
});
test('explicit OB rejects an endpoint and a finite strip crossed between safe endpoints',()=>{
 const h={surface_zones:[zone('f','fairway',-20,0,20,30)],boundary_segments:[ob(-1,14.2,15.4)]},all=surfaces(h);
 assert.equal(classifyLocation(h,false,all,p(0,14.3)),'ob');
 assert.equal(clearGroundRoute(all,p(0,10),p(0,20),h),false);
 assert.equal(clearGroundRoute(all,p(0,10),p(0,14.3),h),false);
 assert.equal(clearGroundRoute(all,p(-2,10),p(-2,20),h),true);
});
test('OB mode is isolated and width stops at white stakes instead of the fairway edge',()=>{
 const h={surface_zones:[zone('f','fairway',-50,220,50,260)],boundary_segments:[ob(3,220,260,true)]},all=surfaces(h);
 assert.ok(Math.abs(landingWidth(all,p(0,240),p(0,0),'fairway',h,true)-53)<.001);
 assert.ok(Math.abs(landingWidth(all,p(0,240),p(0,0),'fairway',h,false)-100)<.001);
 assert.equal(landingWidth(all,p(4,240),p(0,0),'fairway',h,true),0);
 assert.equal(clearGroundRoute(all,p(0,240),p(4,240),h,true),false);
 assert.equal(clearGroundRoute(all,p(0,240),p(4,240),h,false),true);
});
test('touching or travelling along a hazard edge is not a clear rolling corridor',()=>{
 const h={surface_zones:[zone('f','fairway',-20,0,20,30),zone('w','water',0,14,2,16)]},all=surfaces(h);
 assert.equal(clearGroundRoute(all,p(0,10),p(0,20),h),false);
 assert.equal(clearGroundRoute(all,p(-2,12),p(2,16),h),false);
 assert.equal(clearGroundRoute(all,p(-2,10),p(-2,20),h),true);
});
