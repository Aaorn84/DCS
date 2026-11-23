import type {Point} from './roundEngine.ts';
export type XY={x:number;y:number};
export type Surface={id:string;kind:string;rings:number[][][];bounds:number[]};
const RAD=Math.PI/180,EARTH=6371000,YARD=.9144;
export function validPoint(p:any):p is Point{return !!p&&[p.latitude,p.longitude,p.accuracy_m??0].every(Number.isFinite)&&Math.abs(p.latitude)<=90&&Math.abs(p.longitude)<=180&&(p.accuracy_m??0)>=0;}
export function distance(a:Point,b:Point){const lat=(b.latitude-a.latitude)*RAD,lon=(b.longitude-a.longitude)*RAD;const h=Math.sin(lat/2)**2+Math.cos(a.latitude*RAD)*Math.cos(b.latitude*RAD)*Math.sin(lon/2)**2;return 2*EARTH*Math.asin(Math.sqrt(Math.min(1,h)));}
export function frame(origin:Point){const scale=111195*Math.cos(origin.latitude*RAD);if(scale<1)throw Error('unsupported polar coordinates');return {xy:(p:Point):XY=>({x:(p.longitude-origin.longitude)*scale,y:(p.latitude-origin.latitude)*111195}),point:(p:XY):Point=>({longitude:origin.longitude+p.x/scale,latitude:origin.latitude+p.y/111195,accuracy_m:0})};}
function validRing(r:any):r is number[][]{return Array.isArray(r)&&r.length>=4&&r.every(v=>Array.isArray(v)&&v.length===2&&v.every(Number.isFinite)&&Math.abs(v[0])<=180&&Math.abs(v[1])<=90)&&r[0][0]===r.at(-1)[0]&&r[0][1]===r.at(-1)[1];}
const prepared=new WeakMap<object,Map<boolean,Surface[]>>();
export function surfaces(hole:any,simulation=false):Surface[]{
 const cached=prepared.get(hole)?.get(simulation);if(cached)return cached;
 const rows=new Map<string,Surface>();
 function add(id:string,kind:string,rings:any){if(!Array.isArray(rings)||!rings.length||!rings.every(validRing))return;const outer=rings[0];rows.set(id,{id,kind,rings,bounds:[Math.min(...outer.map((v:number[])=>v[0])),Math.min(...outer.map((v:number[])=>v[1])),Math.max(...outer.map((v:number[])=>v[0])),Math.max(...outer.map((v:number[])=>v[1]))]});}
 if(simulation)for(const path of hole.display_paths??[]){const kind=({FairwayTrace:'fairway',GreenTrace:'green',BunkerTrace:'bunker',WaterTrace:'water'} as any)[path.kind];if(!kind||!Array.isArray(path.points)||path.points.length<3)continue;const ring=path.points.map((p:any)=>[p.longitude,p.latitude]);if(JSON.stringify(ring[0])!==JSON.stringify(ring.at(-1)))ring.push(ring[0]);add(String(path.id),kind,[ring]);}
 for(const zone of hole.surface_zones??[])if(zone.verified===true&&zone.source&&zone.geometry?.type==='Polygon'&&['fairway','green','bunker','water','ob'].includes(zone.surface))add(String(zone.id),zone.surface,zone.geometry.coordinates);
 const result=[...rows.values()];const modes=prepared.get(hole)??new Map<boolean,Surface[]>();modes.set(simulation,result);prepared.set(hole,modes);return result;
}
function insideRing(ring:number[][],x:number,y:number,edgeInside:boolean){let hit=false;for(let i=0;i<ring.length-1;i++){const [a,b]=ring[i],[c,d]=ring[i+1];const cross=(x-a)*(d-b)-(y-b)*(c-a);if(Math.abs(cross)<1e-15&&x>=Math.min(a,c)&&x<=Math.max(a,c)&&y>=Math.min(b,d)&&y<=Math.max(b,d))return edgeInside;if((b>y)!==(d>y)&&x<a+(c-a)*(y-b)/(d-b))hit=!hit;}return hit;}
export function contains(surface:Surface,p:Point,edgeInside=false){const [left,bottom,right,top]=surface.bounds,x=p.longitude,y=p.latitude;return x>=left&&x<=right&&y>=bottom&&y<=top&&insideRing(surface.rings[0],x,y,edgeInside)&&!surface.rings.slice(1).some(r=>insideRing(r,x,y,!edgeInside));}
export function classify(all:Surface[],p:Point){return ['ob','water','bunker','green','fairway'].find(kind=>all.some(s=>s.kind===kind&&contains(s,p,true)))??'unknown';}
export function edgeDistance(surface:Surface,p:Point){const f=frame(p);let best=Infinity;for(const ring of surface.rings)for(let i=0;i<ring.length-1;i++){const a=f.xy({longitude:ring[i][0],latitude:ring[i][1],accuracy_m:0}),b=f.xy({longitude:ring[i+1][0],latitude:ring[i+1][1],accuracy_m:0}),dx=b.x-a.x,dy=b.y-a.y,t=Math.max(0,Math.min(1,-(a.x*dx+a.y*dy)/(dx*dx+dy*dy||1)));best=Math.min(best,Math.hypot(a.x+t*dx,a.y+t*dy));}return best;}
/** Exact intersections with the horizontal projected aim segment; crossing is NOT rejection. */
export function crossings(all:Surface[],origin:Point,target:Point){const f=frame(origin),end=f.xy(target),length=Math.hypot(end.x,end.y);if(!length)return [];const ux=end.x/length,uy=end.y/length;
 const out:{id:string;kind:string;near_m:number;far_m:number}[]=[];
 for(const s of all.filter(s=>['bunker','water','ob'].includes(s.kind))){const cuts=[0,length];for(const ring of s.rings)for(let i=0;i<ring.length-1;i++){const a=f.xy({longitude:ring[i][0],latitude:ring[i][1],accuracy_m:0}),b=f.xy({longitude:ring[i+1][0],latitude:ring[i+1][1],accuracy_m:0});const ax=a.x*uy-a.y*ux,bx=b.x*uy-b.y*ux;if((ax<=0&&bx>=0||bx<=0&&ax>=0)&&Math.abs(bx-ax)>1e-9){const t=-ax/(bx-ax),depth=(a.x+(b.x-a.x)*t)*ux+(a.y+(b.y-a.y)*t)*uy;if(depth>0&&depth<length)cuts.push(depth);}}
  cuts.sort((a,b)=>a-b);let near=Infinity,far=0;for(let i=0;i<cuts.length-1;i++){const middle=(cuts[i]+cuts[i+1])/2;if(contains(s,f.point({x:ux*middle,y:uy*middle}),true)){near=Math.min(near,cuts[i]);far=Math.max(far,cuts[i+1]);}}if(near<Infinity)out.push({id:s.id,kind:s.kind,near_m:near,far_m:far});
 }return out;
}
type PreparedBoundary={a:Point;b:Point;local:ReturnType<typeof frame>;axis:XY;length2:number;reference:number};
const preparedBoundaries=new WeakMap<object,Map<boolean,PreparedBoundary[]>>();
function boundaries(hole:any,simulation:boolean):PreparedBoundary[]{
 if(!Array.isArray(hole?.boundary_segments)||!hole.boundary_segments.length)return [];
 const found=preparedBoundaries.get(hole)?.get(simulation);if(found)return found;
 const result:PreparedBoundary[]=[];
 for(const s of hole.boundary_segments){
  if(s.kind!=='ob'||!s.source||s.simulation_only&&!simulation||!validPoint(s.a)||!validPoint(s.b)||!validPoint(s.inside_reference))continue;
  const local=frame(s.a),axis=local.xy(s.b),inside=local.xy(s.inside_reference),length2=axis.x*axis.x+axis.y*axis.y;
  if(length2<1)continue;
  result.push({a:s.a,b:s.b,local,axis,length2,reference:axis.x*inside.y-axis.y*inside.x});
 }
 const modes=preparedBoundaries.get(hole)??new Map<boolean,PreparedBoundary[]>();modes.set(simulation,result);preparedBoundaries.set(hole,modes);return result;
}
const CUT_EPS=1e-10;
type Cut={t:number;blocked:boolean};
/** Partition a finite ground segment at every polygon edge and OB half-strip boundary.
 * The classification is constant inside each resulting open interval.
 */
function groundCuts(all:Surface[],start:Point,end:Point,hole:any,simulation:boolean){
 const f=frame(start),v=f.xy(end),length2=v.x*v.x+v.y*v.y,raw:Cut[]=[{t:0,blocked:false},{t:1,blocked:false}];
 const pointAt=(t:number)=>f.point({x:v.x*t,y:v.y*t});
 function add(t:number,blocked=false){if(t>=-CUT_EPS&&t<=1+CUT_EPS)raw.push({t:Math.max(0,Math.min(1,t)),blocked});}
 if(length2>1e-16){
  const left=Math.min(start.longitude,end.longitude),right=Math.max(start.longitude,end.longitude),bottom=Math.min(start.latitude,end.latitude),top=Math.max(start.latitude,end.latitude);
  for(const surface of all){
   const box=surface.bounds;if(box[2]<left||box[0]>right||box[3]<bottom||box[1]>top)continue;
   const blocked=['ob','water','bunker'].includes(surface.kind);
   for(const ring of surface.rings)for(let i=0;i<ring.length-1;i++){
    const a=f.xy({longitude:ring[i][0],latitude:ring[i][1],accuracy_m:0}),b=f.xy({longitude:ring[i+1][0],latitude:ring[i+1][1],accuracy_m:0}),dx=b.x-a.x,dy=b.y-a.y,den=v.x*dy-v.y*dx;
    if(Math.abs(den)>1e-12){
     const t=(a.x*dy-a.y*dx)/den,u=(a.x*v.y-a.y*v.x)/den;
     if(u>=-CUT_EPS&&u<=1+CUT_EPS)add(t,blocked);
    }else if(Math.abs(a.x*v.y-a.y*v.x)<=1e-9*Math.sqrt(length2)){
     // Collinear contact must not disappear when the route lies on an edge.
     add((a.x*v.x+a.y*v.y)/length2,blocked);add((b.x*v.x+b.y*v.y)/length2,blocked);
    }
   }
  }
  for(const boundary of boundaries(hole,simulation)){
   const a=boundary.local.xy(start),b=boundary.local.xy(end),dx=b.x-a.x,dy=b.y-a.y,axis=boundary.axis;
   const dot=a.x*axis.x+a.y*axis.y,dDot=dx*axis.x+dy*axis.y,cross=axis.x*a.y-axis.y*a.x,dCross=axis.x*dy-axis.y*dx;
   if(Math.abs(dDot)>1e-12){add(-dot/dDot);add((boundary.length2-dot)/dDot);}
   if(Math.abs(dCross)>1e-12)add(-cross/dCross);
  }
 }
 raw.sort((a,b)=>a.t-b.t);const cuts:Cut[]=[];
 for(const cut of raw){const last=cuts.at(-1);if(last&&Math.abs(last.t-cut.t)<=CUT_EPS)last.blocked||=cut.blocked;else cuts.push({...cut});}
 return {cuts,pointAt,length:Math.sqrt(length2)};
}
/** Only verifies motion on the ground; airborne obstacle crossings use crossings(). */
export function clearGroundRoute(all:Surface[],start:Point,end:Point,hole:any={},simulation=false){
 const usable=(p:Point)=>['fairway','green'].includes(classifyLocation(hole,simulation,all,p));
 if(!usable(start)||!usable(end))return false;
 const {cuts,pointAt}=groundCuts(all,start,end,hole,simulation);
 for(let i=0;i<cuts.length;i++){
  if(cuts[i].blocked||!usable(pointAt(cuts[i].t)))return false;
  if(i&&!usable(pointAt((cuts[i-1].t+cuts[i].t)/2)))return false;
 }
 return true;
}
export function landingWidth(all:Surface[],p:Point,origin:Point,kind:string,hole:any={},simulation=false){
 const target=all.filter(s=>s.kind===kind),relevant=all.filter(s=>s.kind===kind||['ob','water','bunker'].includes(s.kind));
 const usable=(q:Point)=>target.some(s=>contains(s,q,true))&&!['ob','water','bunker'].includes(classifyLocation(hole,simulation,relevant,q));
 if(!usable(p))return 0;
 const f=frame(origin),v=f.xy(p),length=Math.hypot(v.x,v.y)||1,side={x:v.y/length,y:-v.x/length};let width=0;
 for(const sign of [-1,1]){
  const end=f.point({x:v.x+side.x*sign*60,y:v.y+side.y*sign*60}),route=groundCuts(relevant,p,end,hole,simulation);
  let reach=route.length;
  for(let i=1;i<route.cuts.length;i++){
   const before=route.cuts[i-1],cut=route.cuts[i];
   if(!usable(route.pointAt((before.t+cut.t)/2))){reach=before.t*route.length;break;}
   if(cut.blocked||!usable(route.pointAt(cut.t))){reach=cut.t*route.length;break;}
  }
  width+=reach;
 }
 return width/YARD;
}

/** Refine the coarse angular grid at mapped landing-arc boundaries, not every degree.
 * Prepared edges and the small radius cache live for this candidate search only.
 */
export function landingOffsets(all:Surface[],origin:Point,heading:number,kind:string,hole:any={},simulation=false){
 const f=frame(origin),targets=all.filter(s=>s.kind===kind);
 type Edge={a:XY;dx:number;dy:number;length2:number;projection:number;min2:number;max2:number;infinite:boolean};
 const edges:Edge[]=[];
 function add(a:XY,b:XY,infinite=false){
  const dx=b.x-a.x,dy=b.y-a.y,length2=dx*dx+dy*dy;if(length2<1e-12)return;
  const projection=-(a.x*dx+a.y*dy)/length2,t=infinite?projection:Math.max(0,Math.min(1,projection));
  edges.push({a,dx,dy,length2,projection,min2:(a.x+t*dx)**2+(a.y+t*dy)**2,max2:infinite?Infinity:Math.max(a.x*a.x+a.y*a.y,b.x*b.x+b.y*b.y),infinite});
 }
 for(const s of all)if(s.kind===kind||['ob','water','bunker'].includes(s.kind)){
  for(const ring of s.rings)for(let i=0;i<ring.length-1;i++)add(f.xy({longitude:ring[i][0],latitude:ring[i][1],accuracy_m:0}),f.xy({longitude:ring[i+1][0],latitude:ring[i+1][1],accuracy_m:0}));
 }
 // A bounded OB half-strip changes classification at its boundary and end caps.
 for(const s of boundaries(hole,simulation)){
  const a=f.xy(s.a),b=f.xy(s.b),dx=b.x-a.x,dy=b.y-a.y;
  add(a,b,true);add(a,{x:a.x-dy,y:a.y+dx},true);add(b,{x:b.x-dy,y:b.y+dx},true);
 }
 type Direction={angle:number;from?:number;to?:number};
 const coarse:Direction[]=Array.from({length:17},(_,i)=>({angle:i*6-48})),cache=new Map<string,Direction[]>();
 return (radius:number,roll_m=0)=>{
  const key=radius+'|'+roll_m,cached=cache.get(key);if(cached)return cached;
  const refined=new Map<number,{width:number;from:number;to:number}>();
  for(let extra=0;extra<=roll_m+1e-8;extra+=2*YARD){
   const r=radius+extra,r2=r*r,cuts=new Set<number>([-48,48]);
   for(const e of edges){
    if(r2<e.min2-1e-7||r2>e.max2+1e-7)continue;
    const x=e.a.x+e.projection*e.dx,y=e.a.y+e.projection*e.dy,d2=r2-x*x-y*y;if(d2<-1e-7)continue;
    const dt=Math.sqrt(Math.max(0,d2)/e.length2);
    for(const t of [e.projection-dt,e.projection+dt]){
     if(!e.infinite&&(t<0||t>1))continue;
     let angle=(Math.atan2(e.a.x+t*e.dx,e.a.y+t*e.dy)-heading)/RAD;angle=(angle+540)%360-180;
     if(angle>=-48&&angle<=48)cuts.add(Number(angle.toFixed(7)));
    }
   }
   const sorted=[...cuts].sort((a,b)=>a-b);
   for(let i=1;i<sorted.length;i++){
    const width=sorted[i]-sorted[i-1];if(width<1e-6)continue;
    const angle=Number(((sorted[i]+sorted[i-1])/2).toFixed(7));if(coarse.some(v=>v.angle===angle))continue;
    const p=f.point({x:Math.sin(heading+angle*RAD)*r,y:Math.cos(heading+angle*RAD)*r});
    if(!targets.some(s=>contains(s,p))||['ob','water','bunker'].includes(classifyLocation(hole,simulation,all,p)))continue;
    if(width>(refined.get(angle)?.width??0))refined.set(angle,{width,from:sorted[i-1],to:sorted[i]});
   }
  }
  // Pathological fragmented maps must not create an unbounded voice-time search.
  const added=[...refined].sort((a,b)=>b[1].width-a[1].width||Math.abs(a[0])-Math.abs(b[0])).slice(0,47).map(([angle,arc])=>({angle,from:arc.from,to:arc.to}));
  const result=[...coarse,...added];if(cache.size>=96)cache.delete(cache.keys().next().value!);cache.set(key,result);return result;
 };
}

/** Explicit bounded boundary segments; never reinterpret an ordinary hole outline as OB. */
export function boundaryRisk(hole:any,p:Point,simulation=false):'ob'|null{
 for(const boundary of boundaries(hole,simulation)){
  const q=boundary.local.xy(p),axis=boundary.axis,t=(q.x*axis.x+q.y*axis.y)/boundary.length2,cross=axis.x*q.y-axis.y*q.x;
  if(t>=-CUT_EPS&&t<=1+CUT_EPS&&(cross*boundary.reference<0||Math.abs(cross)/Math.sqrt(boundary.length2)<=(p.accuracy_m??0)+1e-8))return 'ob';
 }return null;
}
export function classifyLocation(hole:any,simulation:boolean,all:Surface[],p:Point){return boundaryRisk(hole,p,simulation)??classify(all,p);}
