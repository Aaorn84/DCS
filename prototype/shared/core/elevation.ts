/** Optional terrain contract. No guessed altitude, slope or ballistic correction. */
import type {Point} from './roundEngine.ts';
import {distance,validPoint} from './geometry.ts';
export type Elevation={value:number;unit:'m';datum:string;source:string;accuracy_m:number;verified:boolean};
export type TerrainSlope={gradient_percent:number;aspect_degrees:number;source:string;accuracy_percent:number;verified:boolean};
export type TerrainSample={point:Point;elevation:Elevation;support_radius_m:number;slope?:TerrainSlope};
export type TerrainData={schema:1;revision:string;samples:TerrainSample[]};
export type DistanceAssessment={horizontal_yards:number;elevation_change_m:number|null;elevation_uncertainty_m:number|null;playing_distance_yards:null;status:'missing'|'datum_mismatch'|'unvalidated';correction_enabled:false};
export const ELEVATION_MODEL_VERSION=1;
export function validElevation(v:any):v is Elevation{return Boolean(v&&v.unit==='m'&&v.verified===true&&typeof v.value==='number'&&Number.isFinite(v.value)&&v.value>=-500&&v.value<=9000&&typeof v.accuracy_m==='number'&&Number.isFinite(v.accuracy_m)&&v.accuracy_m>=0&&v.accuracy_m<=100&&typeof v.source==='string'&&v.source.trim()&&typeof v.datum==='string'&&v.datum.trim());}
export function validSlope(v:any):v is TerrainSlope{return Boolean(v&&v.verified===true&&Number.isFinite(v.gradient_percent)&&v.gradient_percent>=0&&v.gradient_percent<=100&&Number.isFinite(v.aspect_degrees)&&v.aspect_degrees>=0&&v.aspect_degrees<360&&Number.isFinite(v.accuracy_percent)&&v.accuracy_percent>=0&&typeof v.source==='string'&&v.source.trim());}
/** Bound work to the current hole; a radius is a surveyed support area, not inferred slope. */
export function terrainResolver(hole:any){
 const terrain=hole?.terrain;const samples:TerrainSample[]=terrain?.schema===1&&typeof terrain.revision==='string'&&terrain.revision.trim()&&Array.isArray(terrain.samples)&&terrain.samples.length<=2048?terrain.samples.filter((s:any)=>validPoint(s.point)&&validElevation(s.elevation)&&Number.isFinite(s.support_radius_m)&&s.support_radius_m>=0&&s.support_radius_m<=25):[];
 return (p:Point):Elevation|null=>{
  const own=(p as Point&{elevation?:Elevation}).elevation;if(validElevation(own))return own;
  let result:Elevation|null=null,best=Infinity;
  for(const sample of samples){const gap=distance(p,sample.point);if(gap<=sample.support_radius_m&&gap<best){best=gap;result=sample.elevation;}}
  return result;
 };
}
export function assessDistance(origin:Point,target:Point,resolve:(p:Point)=>Elevation|null=()=>null):DistanceAssessment{
 const base:DistanceAssessment={horizontal_yards:distance(origin,target)/.9144,elevation_change_m:null,elevation_uncertainty_m:null,playing_distance_yards:null,status:'missing',correction_enabled:false};
 const a=resolve(origin),b=resolve(target);if(!a||!b)return base;if(a.datum!==b.datum)return {...base,status:'datum_mismatch'};
 return {...base,elevation_change_m:b.value-a.value,elevation_uncertainty_m:a.accuracy_m+b.accuracy_m,status:'unvalidated'};
}
