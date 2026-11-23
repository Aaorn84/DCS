export type Club={key:string;label:string;low:number;high:number;estimated:boolean;wood:boolean;driver:boolean;role?:string;purposeOnly?:boolean};
const labels:Record<string,string>={driver:'一号木',three_wood:'3号木',five_wood:'5号木',hybrid:'铁木杆',seven:'7号铁',iron3:'3号铁',iron4:'4号铁',pitching_wedge:'P杆'};
export function normalizeClub(label:string){return label.replace(/^1号木$/,'一号木').replace(/^三号木$/,'3号木').replace(/^五号木$/,'5号木').replace(/^混合杆$/,'铁木杆').replace(/^(\d)铁$/,'$1号铁').replace(/^PW?$/i,'P杆');}
export function bag(profile:any):Club[]{
 const result=new Map<string,Club>();
 const add=(key:string,label:string,low:number,high:number,estimated=false,role?:string,purposeOnly=false)=>{if(!Number.isFinite(low)||!Number.isFinite(high)||low<0||high<=0||low>high||high>400)return;label=normalizeClub(label);result.set(label,{key,label,low,high,estimated,wood:/号木$/.test(label),driver:label==='一号木',role,purposeOnly});};
 for(const [key,defaultLabel] of Object.entries(labels)){const v=profile[key]?.value;if(v?.distance_type==='carry'&&['码','米'].includes(v.units)){const d=v.distance/(v.units==='米'?.9144:1);add(key,v.club_name||defaultLabel,d,d);}}
 const seven=result.get('7号铁');if(seven){for(let n=3;n<=9;n++){const label=n+'号铁',d=seven.high+(7-n)*10;if(!result.has(label))add('iron'+n,label,d,d,true);}if(!result.has('P杆'))add('pitching_wedge','P杆',seven.high-30,seven.high-30,true);}
 const long=profile.long_iron?.value;if(long?.distance_type==='carry'&&['码','米'].includes(long.units)&&long.club_name){const d=long.distance/(long.units==='米'?.9144:1);add('long_iron',long.club_name,d,d);}
 const uses=profile.lofted_wedge_uses?.value??{};
 for(const [loft,v] of Object.entries(profile.lofted_wedge_ranges?.value??{}) as [string,any][]){if(['码','米'].includes(v.units)){const scale=v.units==='米'?1/.9144:1;add('wedge'+loft,loft+'度杆',v.low*scale,v.high*scale,false,uses[loft]);}}
 for(const [loft,use] of Object.entries(uses))if(use==='沙坑'&&!result.has(loft+'度杆'))add('wedge'+loft,loft+'度杆',0,30,false,'沙坑',true);
 for(const [label,v] of Object.entries(profile.bag_overrides??{}) as [string,any][])add(label,label,v.low,v.high,false,v.role);
 return [...result.values()];
}
export function fairwayFinder(profile:any){const row=profile.fairway_finder?.value??profile.fairway_finder;return normalizeClub(typeof row==='string'?row:row?.club??row?.label??row?.club_name??'');}
