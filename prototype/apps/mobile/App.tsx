import AsyncStorage from '@react-native-async-storage/async-storage';
import {roundTotals as localTotals,roundChoices as localChoices} from '../../shared/core/runtime.ts';
import {localRuleError} from '../../shared/core/dialogue.ts';
import {OfflineRound} from './src/offlineRound';
import {CourseLibrary} from './src/courseLibrary';
import {setupAnswer,setupChoices,setupPrompt} from './src/localSetup';
import OfflineSetupPanel from './src/OfflineSetupPanel';
import {JourneyPersistence} from './src/journeyPersistence';
import {CheckpointStore} from './src/checkpointStore';
import {JOURNEY_CACHE_PREFIX} from './src/cacheScope';
import {CORE_DATASET} from '../../shared/core/protocol';
import React,{useRef,useState} from 'react';
import {Platform,ScrollView,Text,TextInput,Pressable,StyleSheet,View} from 'react-native';
import {SafeAreaProvider,SafeAreaView} from 'react-native-safe-area-context';
import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import PrivateVoice from './src/PrivateVoice';
import type {SpeakerProfile} from './src/speakerGate';
import {request} from './src/api';
import {Journey,JourneyClient,JourneyResponse} from './src/journey';
import {useVoice} from './src/useVoice';
import {InternationalClient} from './src/international';
import {voiceLocales,type VoiceLocale} from './src/locale';
const stageLabels:Record<string,string>={memory:'先认识一下',name:'怎么称呼你',proactive:'什么时候提醒',shot_recording:'击球记录偏好',driver:'了解一号木',seven:'了解7号铁',miss:'常见偏差',course:'选择球场',tee:'选择发球台',start_hole:'从哪洞开始',ready:'准备出发',active:'球童随时在',finish_confirm:'结束确认',feeling:'听听你的感受',postgame:'赛后聊聊',coach_consent:'你的改善意愿',focus:'只选一个重点',plan_confirm:'确认计划',practice:'回看上次重点',idle:'下次见'};
const durableStore=new CheckpointStore(AsyncStorage,text=>Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,text),key=>key.startsWith(JOURNEY_CACHE_PREFIX)&&!key.includes('.package.'));
function Companion(){
 const [base,setBase]=useState(Platform.OS==='android'?'http://10.0.2.2:8787':'http://localhost:8787');
 const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[input,setInput]=useState('');
 const [j,setJ]=useState<Journey|null>(null),[transcript,setTranscript]=useState<string[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [locale,setLocale]=useState<VoiceLocale>('zh-CN');
 const international=useRef<InternationalClient|null>(null);
 const [showDetails,setShowDetails]=useState(false);
 const [speaker,setSpeaker]=useState<SpeakerProfile|null>(null),[speakerFirst,setSpeakerFirst]=useState(false);
 const speakerKey=useRef('');
 const client=useRef<JourneyClient|null>(null),lock=useRef(false);
 const offline=useRef<OfflineRound|null>(null);
 const library=useRef<CourseLibrary|null>(null);
 const postgame=useRef<JourneyClient|null>(null);
 const [libraryState,setLibraryState]=useState<Awaited<ReturnType<CourseLibrary['read']>>|null>(null);
 const [offlineNotice,setOfflineNotice]=useState('');
 const [localRound,setLocalRound]=useState<any>(null);
 const [needsRecordingRecovery,setNeedsRecordingRecovery]=useState(false);
 const [syncBusy,setSyncBusy]=useState(false);
 const syncGeneration=useRef(0);
 const syncWorker=useRef<OfflineRound|null>(null);
 const log=(who:string,text:string)=>{if(text)setTranscript(v=>[...v,who+'：'+text]);};
 function show(r:JourneyResponse){setJ(r.journey);log('球童',r.result?.text||'');return r;}
 function simulationPoint(kind:string){const point=j?.simulation?.positions?.[kind];if(!point)throw Error('当前球场缺少该模拟位置，请核对地图。');return point;}
 async function submit(type:string,extra:Record<string,unknown>={}){
  if(!client.current)throw Error('请先登录');
  if(localRound)throw Error('本场由离线记分接管，请先同步并结束离线记录。');
  const id=Crypto.randomUUID();return show(await client.current.submit({type,event_id:id,observed_at:new Date().toISOString(),...extra},id,j?.version));
 }
 async function say(text:string):Promise<JourneyResponse>{
  log('你',text);
  if(localRound&&offline.current){
   if(text==='安静'){voice.stop();return {journey:j!,result:{text:'',speak_allowed:false,pause:true}};}
   try{const r=await offline.current.turn(text,Crypto.randomUUID(),new Date().toISOString());setLocalRound(r.local_state);if(r.clock_warning)setOfflineNotice('检测到设备时间回拨，记录仍按事件顺序保存，原始设备时间保留供核对。');log('球童',r.text);return {journey:j!,result:{text:r.text,speak_allowed:true}};}
   catch(error){throw Error(localRuleError(error instanceof Error?error.message:''));}
  }
  if(postgame.current&&j?.stage==='postgame'){const id=Crypto.randomUUID();return show(await postgame.current.submit({type:'message',event_id:id,observed_at:new Date().toISOString(),text},id,j.version));}
  if(library.current){
   if(text.replace(/[\s，,。]/g,'')==='开始球局'){await startLocalRound();return {journey:j!,result:{text:'本场已在本机开始，联网后可同步。',speak_allowed:true}};}
   const disk=await library.current.read();if(text==='安静'){voice.stop();return {journey:j!,result:{text:'',speak_allowed:false,pause:true}};}if(text==='继续')return {journey:j!,result:{text:setupPrompt(disk.draft),speak_allowed:true}};let draft=disk.draft,response='';
   const selected=disk.downloads.find(c=>c.name===text||c.course_id===text);
   if(selected){draft={...draft,course_id:selected.course_id,tee:selected.tee,stage:'tee'};response='已选择'+selected.name+'。'+setupPrompt(draft);}
   else if(draft.stage==='tee'&&disk.downloads.some(c=>c.course_id===draft.course_id&&c.tee===text.replace('台','Tee'))){draft={...draft,tee:text.replace('台','Tee'),stage:'start_hole'};response=setupPrompt(draft);}
   else{const answer=setupAnswer(draft,text);draft=answer.draft;response=answer.text;}
   await library.current.saveDraft(draft);setLibraryState(await library.current.read());log('球童',response);return {journey:j!,result:{text:response,speak_allowed:true}};
  }
  return submit('message',{text});
 }
 async function internationalSay(text:string){
  const current=international.current;
  if(!current)throw Error('请先选择并保存语言');
  if(current.pending)throw Error('请先重试多语言请求');
  const id=Crypto.randomUUID();
  const reply=await current.submit({type:'utterance',event_id:id,observed_at:new Date().toISOString(),text},id);
  log('球童',reply.result?.text||'');
  return {text:reply.result?.speak_allowed?reply.result.text:'',pause:false};
 }
 async function chooseLocale(next:VoiceLocale){
  if(!client.current)return;
  voice.stop();
  const current=international.current ?? new InternationalClient(base,client.current.token);
  international.current=current;
  if(next==='zh-CN'){setLocale(next);return;}
  if(current.pending)await current.retry();
  const id=Crypto.randomUUID();
  await current.submit({type:'configure',event_id:id,observed_at:new Date().toISOString(),configuration:{locale:next}},id);
  setLocale(next);
 }
 async function handleVoice(text:string){
  if(lock.current)throw Error('正在处理上一条请求');lock.current=true;setBusy(true);
  try{if(locale!=='zh-CN')return await internationalSay(text);const r=await say(text);return {text:r.result?.speak_allowed?r.result.text:'',pause:r.result?.pause||r.journey.quiet};}
  finally{lock.current=false;setBusy(false);}
 }
 const voice=useVoice(text=>speaker?.enabled||speakerFirst?Promise.resolve({text:'',pause:true}):handleVoice(text),locale,Boolean(localRound)||Boolean(library.current));
 async function run(fn:()=>Promise<unknown>){if(lock.current)return;lock.current=true;setBusy(true);setError('');try{await fn();}catch(e){setError(e instanceof Error?e.message:'请求失败');}finally{lock.current=false;setBusy(false);}}
 async function resumeJourney(){
  if(library.current){setLibraryState(await library.current.read());const record=await library.current.active();if(record)await openLocalRound(record.id);return;}
  if(client.current){await client.current.restore();if(client.current.pending)show(await client.current.retry());else show(await client.current.snapshot());}
 }
 function setupSnapshot():JourneyResponse{return {journey:{stage:'course',distance_unit:'码',version:0,question:'本机准备',choices:[],quiet:false,memory_allowed:null,profile:{},round:null,history:[],coach:{enabled:false},score_summary:{confirmed_holes:0,confirmed_subtotal:null}}};}
 async function openLocalRound(id:string){
  const books=library.current;if(!books||!client.current)return;
  await offline.current?.cancelSynchronization();const record=await books.select(id);
  const worker=new OfflineRound(base,client.current.token,durableStore,record.key,()=>Crypto.randomUUID(),text=>Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,text));
  const cached=record.phase==='preparing'?await worker.beginOffline(await books.materialize(record)):await worker.verifyCached();
  if(record.phase==='preparing')await books.activate(record.id);
  offline.current=worker;setLocalRound(cached.local_state);setNeedsRecordingRecovery(Boolean(cached.native_start&&cached.lease?.status==='released'&&!cached.local_state.finished));setLibraryState(await books.read());setLocale('zh-CN');setOfflineNotice('本机球局已打开；记分与策略无需网络。');
 }
 async function startLocalRound(){
  if(!library.current)return;
  if(offline.current){const cached=await offline.current.cached();if(cached.local_state&&!cached.local_state.finished)throw Error('请先完成当前球局，不能覆盖正在打的记录。');}
  postgame.current=null;const record=await library.current.prepareLocalRound();await openLocalRound(record.id);
 }
 async function auth(register:boolean){
  syncGeneration.current++;await offline.current?.cancelSynchronization();setSyncBusy(false);syncWorker.current=null;voice.stop();
  const r=await request(base,register?'/auth/register':'/auth/login',undefined,{email,password});
  const cacheKey=JOURNEY_CACHE_PREFIX+await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,base.trim().replace(/\/+$/,'')+'|'+r.user.id);
  const next=new JourneyClient(base,r.token,new JourneyPersistence(durableStore,cacheKey));
  const snapshot=setupSnapshot();
  let profile:SpeakerProfile|null=null;let key='';
  if(Platform.OS!=='web'){
   key='caddie.speaker.'+await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,base.trim().replace(/\/+$/,'')+'|'+r.user.id);
   const stored=await SecureStore.getItemAsync(key);
   if(stored!==null){
    const parsed:SpeakerProfile=JSON.parse(stored);
    if(typeof parsed.enabled!=='boolean'||(parsed.enabled&&!parsed.template))throw Error('本机声纹设置无法读取。');
    profile=parsed;
   }
  }
  speakerKey.current=key;setSpeaker(profile);client.current=next;offline.current=null;library.current=new CourseLibrary(base,r.token,durableStore,cacheKey+'.library',()=>Crypto.randomUUID(),text=>Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,text));await library.current.read().then(setLibraryState);setOfflineNotice('');setLocalRound(null);setNeedsRecordingRecovery(false);
  if(Platform.OS!=='web')await SecureStore.setItemAsync('caddie.lastOfflineSession',JSON.stringify({dataset:CORE_DATASET,base,email:email.trim().toLowerCase(),token:r.token,user_id:r.user.id,cacheKey}),{keychainAccessible:SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY});
  setPassword('');setTranscript([]);setJ(snapshot.journey);
  const first=Platform.OS!=='web'&&profile===null;
  setSpeakerFirst(first);if(!first)await resumeJourney();
 }
 async function syncInBackground(){
  const worker=offline.current;if(!worker||syncWorker.current)return;syncWorker.current=worker;const epoch=syncGeneration.current;setSyncBusy(true);
  try{await worker.synchronize();if(epoch===syncGeneration.current&&offline.current===worker)setOfflineNotice('本次同步完成，后续新记录仍可在本机继续保存。');}
  catch(error){if(epoch===syncGeneration.current&&offline.current===worker)setError(error instanceof Error?error.message:'同步未完成，本机记录保留。');}
  finally{if(syncWorker.current===worker)syncWorker.current=null;if(epoch===syncGeneration.current&&offline.current===worker)setSyncBusy(false);}
 }
 async function restoreOffline(){
  if(Platform.OS==='web')throw Error('离线账号恢复仅用于原生设备。');
  const raw=await SecureStore.getItemAsync('caddie.lastOfflineSession');if(!raw)throw Error('本机没有可恢复的离线登录，请先联网登录并准备离线球局。');
  const saved=JSON.parse(raw);if(!saved.user_id||saved.dataset!==CORE_DATASET||!saved.cacheKey?.startsWith(JOURNEY_CACHE_PREFIX))throw Error('本机球局版本与当前应用不匹配，请保留记录并联网核对。');const next=new JourneyClient(saved.base,saved.token,new JourneyPersistence(durableStore,saved.cacheKey));
  const books=new CourseLibrary(saved.base,saved.token,durableStore,saved.cacheKey+'.library',()=>Crypto.randomUUID(),text=>Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,text));
  const snapshot=setupSnapshot();const storedLibrary=await books.read();
  const speakerStorageKey='caddie.speaker.'+await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,saved.base.trim().replace(/\/+$/,'')+'|'+saved.user_id);
  const savedSpeaker=await SecureStore.getItemAsync(speakerStorageKey);const restoredSpeaker:SpeakerProfile|null=savedSpeaker?JSON.parse(savedSpeaker):null;
  if(restoredSpeaker&&(typeof restoredSpeaker.enabled!=='boolean'||restoredSpeaker.enabled&&!restoredSpeaker.template))throw Error('本机声纹设置无法读取，请保留记录并联网核对。');
  speakerKey.current=speakerStorageKey;
  setBase(saved.base);setEmail(saved.email);setPassword('');client.current=next;offline.current=null;library.current=books;setLibraryState(storedLibrary);setJ(snapshot.journey);setLocalRound(null);setNeedsRecordingRecovery(false);setLocale('zh-CN');setSpeaker(restoredSpeaker);setSpeakerFirst(false);setOfflineNotice('已恢复本机身份、资料与下载目录，无需连接服务器。');
  const record=await books.active();if(record){const worker=new OfflineRound(saved.base,saved.token,durableStore,record.key,()=>Crypto.randomUUID(),text=>Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,text));const cached=record.phase==='preparing'?await worker.beginOffline(await books.materialize(record)):await worker.verifyCached();if(record.phase==='preparing')await books.activate(record.id);offline.current=worker;setLocalRound(cached.local_state);setNeedsRecordingRecovery(Boolean(cached.native_start&&cached.lease?.status==='released'&&!cached.local_state.finished));setLibraryState(await books.read());}
 }
 async function saveSpeaker(profile:SpeakerProfile){
  voice.stop();
  if(speakerKey.current)await SecureStore.setItemAsync(speakerKey.current,JSON.stringify(profile),
    {keychainAccessible:SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY});
  setSpeaker(profile);
  if(speakerFirst){setSpeakerFirst(false);await resumeJourney();}
 }
 const button=(title:string,fn:()=>Promise<unknown>,disabled=false)=><Pressable key={title} accessibilityRole="button" disabled={busy||disabled} onPress={()=>void run(fn)} style={[styles.button,(busy||disabled)&&{opacity:.4}]}><Text style={{color:'white'}}>{title}</Text></Pressable>;
 const field=(label:string,value:string,change:(s:string)=>void,secret=false)=><TextInput accessibilityLabel={label} placeholder={label} value={value} onChangeText={change} secureTextEntry={secret} autoCapitalize="none" editable={!busy} style={styles.input}/>;
 let choices=localRound?localChoices(localRound):j?.stage==='postgame'?j.choices:libraryState?setupChoices(libraryState.draft):j?.quiet?['继续']:j?.stage==='active'&&!j?.choices.length?['这杆怎么打','还有多少'+(j?.distance_unit||'码'),'这洞六杆','两推','没有罚杆','确认','结束球局']:j?.stage==='idle'?['下一场']:j?.choices||[];
 if(['memory','name','proactive','shot_recording','driver','driver_kind','seven','seven_kind','miss'].includes(j?.stage||''))choices=[...choices,'先打球，稍后了解'];
 return <SafeAreaView style={{flex:1,backgroundColor:'#f1f5ee'}}><ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled"><Text style={styles.title}>电子球童 · 陪你完整打一场</Text><Text style={styles.note}>首次认识 → 赛前沟通 → 场中服务 → 回顾 → 下一场。可选凤凰山来源坐标演示或合成球场；GPS用按钮模拟，来源路径未作实地核验，原生语音仅限前台。操作日志用于恢复与审计，跨场档案由你选择。</Text>
 {!!error&&<Text accessibilityLiveRegion="polite" style={{color:'#a32b20'}}>{error}</Text>}
 {!client.current?<View style={styles.card}>{field('测试API地址',base,setBase)}{field('测试邮箱',email,setEmail)}{field('密码（至少10字符）',password,setPassword,true)}{button('注册并开始',()=>auth(true))}{button('登录并恢复',()=>auth(false))}{Platform.OS!=='web'&&button('恢复本机离线球局',restoreOffline)}</View>:speakerFirst?<View style={styles.card}><Text style={styles.heading}>第一步：让球童认出你的声音</Text><PrivateVoice profile={speaker} firstUse disabled={busy} beforeCapture={voice.stop} save={saveSpeaker} onUtterance={handleVoice}/></View>:<>
 {!localRound&&j?.stage!=='postgame'&&libraryState&&<OfflineSetupPanel library={library.current!} state={libraryState} busy={busy} answer={say} run={fn=>void run(fn)} refresh={async()=>{if(library.current)setLibraryState(await library.current.catalog());}} download={async(id,tee)=>{if(library.current){setLibraryState(await library.current.download(id,tee));setOfflineNotice('球场资料已完整下载并校验，可以离线选择和开局。');}}} remove={async(id,tee)=>{if(library.current)setLibraryState(await library.current.remove(id,tee));}} start={startLocalRound} open={openLocalRound}/>}
 <View style={styles.card}><Text style={styles.heading}>{localRound?'离线记分 · 第'+localRound.hole+'洞':stageLabels[j?.stage||'']||'加载中'}</Text>{transcript.slice(-16).map((t,i)=><Text key={i} style={styles.dialogue}>{t}</Text>)}{choices.map(t=>button(t,()=>t==='下一场'?submit('next_round'):say(t)))}{field('回答当前问题，或继续聊天',input,setInput)}{button('发送',async()=>{const text=input.trim();if(text){if(locale==='zh-CN')await say(text);else{log('你',text);await internationalSay(text);}setInput(current=>current===text?'':current);}})}{!speaker?.enabled&&<><Text style={styles.note}>语音语言 · 外语使用独立的多语言测试球局</Text>{!localRound&&voiceLocales.map(language=>button((locale===language?'✓ ':'')+language,()=>chooseLocale(language)))}{locale!=='zh-CN'&&button('重试多语言请求',async()=>{const current=international.current;if(current?.pending){const response=await current.retry();log('球童',response.result?.text||'');}})}</>}{!speaker?.enabled&&button(voice.enabled?'暂停语音':'开启前台语音',async()=>{if(voice.enabled)voice.stop();else await voice.start();})}{!speaker?.enabled&&<Text style={styles.note}>{voice.status}</Text>}<PrivateVoice profile={speaker} firstUse={false} disabled={busy} beforeCapture={voice.stop} save={saveSpeaker} onUtterance={handleVoice}/>{button('安静',()=>say('安静'))}</View>
 <View style={styles.card}>{localRound&&<><Text style={styles.heading}>本机离线记录</Text><Text>已确认{localTotals(localRound).holes}洞 · {localTotals(localRound).total}杆 · {localTotals(localRound).putts}推 · {localTotals(localRound).penalties}罚杆</Text><Text style={styles.note}>规则、距离、障碍和击球策略均由本机共用核心计算。未知球位保持未知，请在球旁更新定位；演示地图不能替代现场核对。</Text></>}<Text style={styles.heading}>这一场与我们的默契</Text><Text>{localRound?`${libraryState?.catalog.find(c=>c.course_id===localRound.course_id)?.name??localRound.course_id} · ${localRound.tee}`:j?.round?`${j.round.id} · ${j.course_name||'合成球场'} · ${j.round.tee||'发球台未知'}`:'尚未开始球局'}</Text><Text>{localRound?'上方为本机最新记录，服务器成绩在同步后更新。':`已确认${j?.score_summary.confirmed_holes||0}洞，小计${j?.score_summary.confirmed_subtotal??'未知'}杆`}</Text><Text>距离单位：{j?.distance_unit||'码'}</Text><Text>教练：{j?.coach.enabled?'已开启 · '+(j.coach.plan?.focus||'等待确认重点'):'关闭'}</Text><Text>{(libraryState?libraryState.draft.memory_allowed:j?.memory_allowed)?'跨场记住确认资料':(libraryState||j?.memory_allowed===false)?'仅本场':'记忆意愿待确认'}</Text>
 {!library.current&&button('提交模拟发球台位置',()=>submit('gps',{data:simulationPoint('tee')}),j?.stage!=='active')}{button('提交模拟设备位置',()=>submit('gps',{data:simulationPoint('fairway')}),j?.stage!=='active')}{button('读取保存状态',async()=>{if(localRound&&offline.current){const saved=await offline.current.verifyCached();setLocalRound(saved.local_state);setNeedsRecordingRecovery(Boolean(saved.native_start&&saved.lease?.status==='released'&&!saved.local_state.finished));setOfflineNotice('已读取本机保存的最新记录，未发起网络请求。');}else if(client.current)show(await client.current.snapshot());})}{button('重试原请求',async()=>{if(client.current){const channel=postgame.current??client.current;const sent=channel.pending?.event?.text;show(await channel.retry());if(sent)setInput(current=>current===sent?'':current);}},!(postgame.current??client.current)?.pending)}{button('关闭教练',()=>say('关闭教练'))}{button('下一场',async()=>{if(library.current&&(localRound?.finished||j?.stage==='postgame')){await offline.current?.cancelSynchronization();offline.current=null;setLocalRound(null);setNeedsRecordingRecovery(false);setLibraryState(await library.current.nextSetup());}else await submit('next_round');},library.current?!localRound?.finished&&j?.stage!=='postgame':!['postgame','idle'].includes(j?.stage||''))}
 {button(showDetails?'收起测试记录':'高级：查看测试记录',async()=>setShowDetails(!showDetails))}{showDetails&&<Text selectable style={styles.note}>{JSON.stringify({profile:j?.profile,history:j?.history,coach:j?.coach},null,2)}</Text>}
 {localRound&&button('采用本洞发球台参考点（模拟）',async()=>{if(!offline.current)return;const disk=await offline.current.cached();const hole=disk.package.package.course.holes.find((h:any)=>h.number===localRound.hole);const p=hole?.simulation_positions?.tee;if(!p)throw Error('本洞没有发球台模拟参考点，可输入“球位 纬度,经度”确认坐标。');const r=await offline.current.execute('set_position',{point:{latitude:p.latitude,longitude:p.longitude,accuracy_m:p.accuracy_m??0}},Crypto.randomUUID(),new Date().toISOString());setLocalRound(r);setOfflineNotice('已采用地图参考坐标，仅用于模拟，未生成击球。');})}
 {localRound&&<Pressable accessibilityRole="button" disabled={syncBusy} onPress={()=>void syncInBackground()} style={[styles.button,syncBusy&&{opacity:.4}]}><Text style={{color:'white'}}>{syncBusy?'后台同步中，记分可继续':'联网同步离线记录'}</Text></Pressable>}
 {localRound&&needsRecordingRecovery&&button('恢复未结束球局的记录权',async()=>{if(offline.current){const saved=await offline.current.recoverReleasedRound();setLocalRound(saved.local_state);setNeedsRecordingRecovery(Boolean(saved.native_start&&saved.lease?.status==='released'&&!saved.local_state.finished));setOfflineNotice('已恢复本场记分，可继续打球。');}},syncBusy)}
 {localRound&&button('同步并结束离线记分',async()=>{if(!offline.current||!client.current)return;await offline.current.synchronize();await offline.current.release();const disk=await offline.current.cached();if(disk.native_start){const row=await library.current?.active();postgame.current=new JourneyClient(base,client.current.token,new JourneyPersistence(durableStore,(row?.key??'native')+'.postgame'),'/offline-rounds',{round_id:disk.lease.round_id,device_id:disk.device_id,lease_id:disk.lease.lease_id});}const latest=postgame.current?await postgame.current.snapshot():await client.current.snapshot();setLocalRound(null);setNeedsRecordingRecovery(false);show(latest);if(library.current)setLibraryState(await library.current.read());setOfflineNotice('已同步并结束离线记分。');},syncBusy||!localRound.finished)}
 {offlineNotice&&<Text style={styles.note}>{offlineNotice}</Text>}
 {button('退出',async()=>{syncGeneration.current++;await offline.current?.cancelSynchronization();setSyncBusy(false);syncWorker.current=null;voice.stop();if(client.current)await request(base,'/auth/logout',client.current.token,{}).catch(()=>{});if(Platform.OS!=='web')await SecureStore.deleteItemAsync('caddie.lastOfflineSession');setLocalRound(null);setNeedsRecordingRecovery(false);client.current=null;offline.current=null;library.current=null;postgame.current=null;setLibraryState(null);setOfflineNotice('');international.current=null;setLocale('zh-CN');speakerKey.current='';setSpeaker(null);setSpeakerFirst(false);setJ(null);setTranscript([]);})}</View></>}
 </ScrollView></SafeAreaView>;
}
export default function App(){return <SafeAreaProvider><Companion/></SafeAreaProvider>}
const styles=StyleSheet.create({page:{padding:20,maxWidth:850,width:'100%',alignSelf:'center'},title:{fontSize:26,fontWeight:'700',color:'#1d513b'},heading:{fontSize:18,fontWeight:'600',marginBottom:12,color:'#1d513b'},note:{fontSize:12,lineHeight:20,color:'#65796a',marginVertical:8},card:{padding:18,backgroundColor:'white',borderRadius:15,marginVertical:10},button:{padding:12,backgroundColor:'#215d43',borderRadius:9,marginVertical:5},input:{borderWidth:1,borderColor:'#d2dfcf',borderRadius:8,padding:12,marginVertical:6},dialogue:{fontSize:15,lineHeight:24,paddingVertical:6,color:'#294738'}});
