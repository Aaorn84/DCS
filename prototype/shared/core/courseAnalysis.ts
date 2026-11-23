import {assessDistance,terrainResolver,type DistanceAssessment} from './elevation.ts';
/** Course-local geometry and observations. No rules mutation or user preference ranking. */
import type {Club} from './bag.ts';
import {normalizeClub} from './bag.ts';
import {frame,validPoint,distance,contains,clearGroundRoute,classifyLocation,crossings,landingWidth,landingOffsets,edgeDistance,type Surface} from './geometry.ts';
import type {Point} from './roundEngine.ts';
import {planningPattern} from './personalStrategy.ts';
import {systemRisk} from './strategyPolicy.ts';
export type Candidate={distance_assessment?:DistanceAssessment;remaining_distance_assessment?:DistanceAssessment;obstacle_distance_assessments?:DistanceAssessment[];purpose_only:boolean;target_surface:string;aim_label?:string;club:string;club_key:string;carry_yards:number;estimated:boolean;aim_point:Point;landing_point:Point;remaining_yards:number;width_yards:number;roll_yards:number;crossings:ReturnType<typeof crossings>;penalty_samples:number;bunker_samples:number;rough_samples:number;history_weight:number;risk:number;nearby:string[];dispersion_source:string;progress:number};
const YARD=.9144;
function historyWeight(pack:any,hole:number,origin:Point,target:Point,club:string){
 let failures=0;const seen=new Set<string>();const recent=(pack.history_by_hole?.[String(hole)]??[]).slice(0,500);
 for(const row of recent){if(row.club&&normalizeClub(row.club)!==club||row.distance_valid===false||!validPoint(row.origin)||!validPoint(row.landing)||distance(origin,row.origin)>25)continue;if(distance(target,row.landing)>Math.max(25,distance(origin,target)*.25))continue;const key=row.round_id+'|'+row.id;if(seen.has(key))continue;seen.add(key);if(row.hazards?.length)failures++;}
 return Math.min(3,Math.max(0,failures-1));
}
export function courseCandidates(pack:any,model:any,hole:any,all:Surface[],clubs:Club[],surface:'fairway'|'green',origin:Point,green:Point,roll=false):Candidate[]{
 const f=frame(origin),v=f.xy(green),heading=Math.atan2(v.x,v.y),initial=distance(origin,green)/YARD,profile=model.profile??pack.profile??{},out:Candidate[]=[];
 const terrain=terrainResolver(hole);
 const offsets=landingOffsets(all,origin,heading,surface,hole,pack.course.reference_simulation===true);
 for(const club of clubs){
  const carries=club.low===club.high?[club.high]:[...new Set([Math.min(club.high,Math.max(club.low,initial)),club.high,Math.max(club.low,Math.min(club.high,initial-6))])];
  for(const carry of carries){if(carry<1)continue;const envelope=planningPattern(pack.dispersion,profile,club,carry),spread=envelope.lateral+(origin.accuracy_m??0);
   const canRoll=surface==='green'&&roll&&!club.driver&&(club.wood||/铁木杆|^[3-5]号铁$/.test(club.label));
   const covered:number[]=[];
   for(const direction of offsets(carry*YARD,canRoll?10*YARD:0)){
    if(direction.from!==undefined&&covered.some(angle=>angle>direction.from!&&angle<direction.to!))continue;
    const offset=direction.angle;
    const angle=heading+offset*Math.PI/180,ux=Math.sin(angle),uy=Math.cos(angle),m=carry*YARD;
    const landing=f.point({x:ux*m,y:uy*m});let endpoint=landing,rollYards=0;
    if(!all.some(s=>s.kind===surface&&contains(s,landing))){
     if(surface!=='green'||!roll||club.driver||!(club.wood||/铁木杆|^[3-5]号铁$/.test(club.label)))continue;
     for(let extra=2;extra<=10;extra+=2){
      const end=f.point({x:ux*(m+extra*YARD),y:uy*(m+extra*YARD)});
      if(!all.some(s=>s.kind==='green'&&contains(s,end)))continue;
      if(clearGroundRoute(all,landing,end,hole,pack.course.reference_simulation===true)){endpoint=end;rollYards=extra;break;}
     }if(!rollYards)continue;
    }
    if([landing,endpoint].some(p=>['ob','water','bunker'].includes(classifyLocation(hole,pack.course.reference_simulation===true,all,p))))continue;
    const crossing=crossings(all,origin,landing);if(crossing.some(c=>c.far_m+Math.max(3,origin.accuracy_m??0)>m))continue;
    let penalty=0,bunker=0,rough=0;for(let n=0;n<12;n++){const t=n*Math.PI/6,x=ux*(m+Math.cos(t)*envelope.longitudinal)+uy*(Math.sin(t)*spread+envelope.bias),y=uy*(m+Math.cos(t)*envelope.longitudinal)-ux*(Math.sin(t)*spread+envelope.bias),kind=classifyLocation(hole,pack.course.reference_simulation===true,all,f.point({x,y}));if(['ob','water'].includes(kind))penalty++;else if(kind==='bunker')bunker++;else if(!['green','fairway'].includes(kind))rough++;}
    const nearby=all.filter(s=>['ob','water','bunker'].includes(s.kind)&&edgeDistance(s,endpoint)<Math.max(8,spread)).map(s=>s.kind);
    const remaining=distance(landing,green)/YARD,width=landingWidth(all,endpoint,origin,surface,hole,pack.course.reference_simulation===true),weight=historyWeight(pack,hole.number,origin,landing,club.label);
    let aimLabel:string|undefined;
    if(surface==='fairway'){
     const nearbyBunker=all.filter(s=>s.kind==='bunker').map(s=>({s,d:edgeDistance(s,landing)})).sort((a,b)=>a.d-b.d)[0];
     if(nearbyBunker&&nearbyBunker.d<65){const vertices=nearbyBunker.s.rings[0].slice(0,-1);const center={longitude:vertices.reduce((n,v)=>n+v[0],0)/vertices.length,latitude:vertices.reduce((n,v)=>n+v[1],0)/vertices.length,accuracy_m:0};const b=f.xy(center),aim=f.xy(landing),g=f.xy(green);const side=b.x*g.y-b.y*g.x>=0?'右侧':'左侧',aimSide=aim.x*b.y-aim.y*b.x>=0?'右侧':'左侧';aimLabel=`${side}约${Math.round(distance(origin,center)/YARD)}码的沙坑${aimSide}球道`;}
    }
    if(penalty===0&&bunker===0&&weight===0)covered.push(offset);
    out.push({obstacle_distance_assessments:crossing.map(c=>assessDistance(origin,f.point({x:ux*c.far_m,y:uy*c.far_m}),terrain)),distance_assessment:assessDistance(origin,landing,terrain),remaining_distance_assessment:assessDistance(landing,green,terrain),purpose_only:Boolean(club.purposeOnly),target_surface:surface,...(aimLabel?{aim_label:aimLabel}:{}),club:club.label,club_key:club.key,carry_yards:carry,estimated:club.estimated,aim_point:endpoint,landing_point:landing,remaining_yards:remaining,width_yards:width,roll_yards:rollYards,crossings:crossing,penalty_samples:penalty,bunker_samples:bunker,rough_samples:rough,history_weight:weight,risk:systemRisk({penalty_samples:penalty,bunker_samples:bunker,rough_samples:rough,history_weight:weight}),nearby:[...new Set(nearby)],dispersion_source:envelope.source,progress:initial-remaining});
   }
  }
 }
 return out;
}
