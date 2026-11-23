/** Persistent backend host. No filesystem/network access in the domain modules. */
import readline from 'node:readline';
import {profileFacts,profileFromFacts} from './profileMemory.ts';
import {coreFor,isCoreRuleError,SUPPORTED_CORES} from './runtime.ts';
import {CoreRuleError} from './roundEngine.ts';
const packages=new Map();let packageBytes=0;
function execute(request){
 const engine=coreFor(request.core_version);
 for(const obj of [request.package,request.state,request.asset])if(obj&&obj.core_version!==engine.version)throw new CoreRuleError('shared core version mismatch');
 switch(request.method){
  case 'register_package':{
   const bytes=Buffer.byteLength(JSON.stringify(request.package));
   if(typeof request.package_key!=='string'||request.package_key.length>1024||bytes>16*1024*1024||request.package.core_version!==engine.version)throw new CoreRuleError('invalid shared package');
   const old=packages.get(request.package_key);if(old)packageBytes-=old.bytes;packages.delete(request.package_key);packages.set(request.package_key,{package:request.package,bytes});packageBytes+=bytes;
   while(packages.size>8||packageBytes>32*1024*1024){const key=packages.keys().next().value;packageBytes-=packages.get(key).bytes;packages.delete(key);}return {registered:true};
  }
  case 'web_event_cached':{
   const item=packages.get(request.package_key);if(!item)throw new CoreRuleError('shared package not cached');
   if(item.package.core_version!==engine.version)throw new CoreRuleError('shared core version mismatch');
   packages.delete(request.package_key);packages.set(request.package_key,item);return engine.webJourneyTurn(item.package,request.state,request.event,request.context);
  }
  case 'plan_cached':{
   const item=packages.get(request.package_key);if(!item)throw new CoreRuleError('shared package not cached');
   if(item.package.core_version!==engine.version)throw new CoreRuleError('shared core version mismatch');
   packages.delete(request.package_key);packages.set(request.package_key,item);return engine.planStrategy(item.package,request.state,request.intent);
  }
  case 'offline_package_wire':{const value=engine.assembleOfflinePackage(request.asset,request.context,request.setup,request.round);return {package:value,payload_json:engine.canonicalJson(value)};}
  case 'assemble_offline_package':return engine.assembleOfflinePackage(request.asset,request.context,request.setup,request.round);
  case 'plan':return engine.planStrategy(request.package,request.state,request.intent);
  case 'parse':return engine.parseLocalTurn(request.state,request.text);
  case 'choices':return engine.localChoices(request.state);
  case 'create':return engine.createLocalRound(request.package);
  case 'apply':return engine.applyLocalCommand(request.state,request.event);
  case 'totals':return engine.localTotals(request.state);
  case 'profile_memory':return {fields:profileFacts(request.profile),clocks:request.profile?.field_versions??{}};
  case 'profile_from_facts':return profileFromFacts(request.fields,request.clocks);
  case 'capabilities':return {core_version:engine.version,dataset:engine.dataset,supported_core_versions:SUPPORTED_CORES};
  default:throw new CoreRuleError('unsupported shared core operation');
 }
}
const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
for await(const line of lines){
 let reply;
 try{const request=JSON.parse(line);reply={ok:true,result:execute(request)};}
 catch(error){reply={ok:false,kind:isCoreRuleError(error)?'rule':'internal',error:isCoreRuleError(error)?error.message:'shared core execution failed'};}
 process.stdout.write(JSON.stringify(reply)+'\n');
}
