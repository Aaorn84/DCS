import type {OfflineRound} from './offlineRound.ts';
import type {JourneyClient} from './journey.ts';
/** Cold restoration must be entirely local, including an interrupted preparation. */
export async function readOfflineSession(local:OfflineRound,journey:JourneyClient){
 const cached=await local.cached();const preparing=Boolean(cached.prepare_intent||cached.lease?.status==='preparing');
 if(cached.local_state&&!cached.package)throw Error('本机离线包缺失，请保留记录并联网核对。');
 const disk=preparing&&!cached.package?cached:await local.verifyCached();
 const snapshot=await journey.cachedSnapshot();
 if(!snapshot||!preparing&&(!disk.local_state||disk.lease?.status!=='active'))throw Error('本机没有已准备的离线记分球局。');
 return {disk,snapshot,preparing};
}
