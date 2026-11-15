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
const stageLabels:Record<string,string>={memory:'先认识一下',name:'怎么称呼你',proactive:'什么时候提醒',shot_recording:'击球记录偏好',driver:'了解一号木',driver_kind:'确认距离类型',seven:'了解7号铁',seven_kind:'确认距离类型',miss:'常见偏差',course:'选择球场',tee:'选择发球台',start_hole:'从哪洞开始',goal:'今天想怎样打',condition:'今天的状态',ready:'准备出发',active:'球童随时在',finish_confirm:'结束确认',feeling:'听听你的感受',postgame:'赛后聊聊',coach_consent:'你的改善意愿',focus:'只选一个重点',plan_confirm:'确认计划',practice:'回看上次重点',idle:'下次见'};
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
 const log=(who:string,text:string)=>{if(text)setTranscript(v=>[...v,who+'：'+text]);};
 function show(r:JourneyResponse){setJ(r.journey);log('球童',r.result?.text||'');return r;}
 async function submit(type:string,extra:Record<string,unknown>={}){
  if(!client.current)throw Error('请先登录');
  const id=Crypto.randomUUID();return show(await client.current.submit({type,event_id:id,observed_at:new Date().toISOString(),...extra},id,j?.version));
 }
 async function say(text:string){log('你',text);return submit('message',{text});}
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
 const voice=useVoice(text=>speaker?.enabled||speakerFirst?Promise.resolve({text:'',pause:true}):handleVoice(text),locale);
 async function run(fn:()=>Promise<unknown>){if(lock.current)return;lock.current=true;setBusy(true);setError('');try{await fn();}catch(e){setError(e instanceof Error?e.message:'请求失败');}finally{lock.current=false;setBusy(false);}}
 async function resumeJourney(){
  if(!client.current)return;
  const snapshot=await client.current.snapshot();setJ(snapshot.journey);
  await client.current.submit({type:'resume',event_id:Crypto.randomUUID(),observed_at:new Date().toISOString()},Crypto.randomUUID(),snapshot.journey.version).then(show);
 }
 async function auth(register:boolean){
  voice.stop();
  const r=await request(base,register?'/auth/register':'/auth/login',undefined,{email,password});
  const next=new JourneyClient(base,r.token);
  const snapshot=await next.snapshot();
  let profile:SpeakerProfile|null=null;let key='';
  if(Platform.OS!=='web'){
   key='caddie.speaker.'+await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,base.trim().replace(/\/+$/,'')+'|'+email.trim().toLowerCase());
   const stored=await SecureStore.getItemAsync(key);
   if(stored!==null){
    const parsed:SpeakerProfile=JSON.parse(stored);
    if(typeof parsed.enabled!=='boolean'||(parsed.enabled&&!parsed.template))throw Error('本机声纹设置无法读取。');
    profile=parsed;
   }
  }
  speakerKey.current=key;setSpeaker(profile);client.current=next;
  setPassword('');setTranscript([]);setJ(snapshot.journey);
  const first=Platform.OS!=='web'&&snapshot.journey.stage==='memory'&&profile===null;
  setSpeakerFirst(first);if(!first)await resumeJourney();
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
 let choices=j?.quiet?['继续']:j?.stage==='active'&&!j?.choices.length?['这杆怎么打','还有多少'+(j?.distance_unit||'码'),'这洞六杆','两推','没有罚杆','确认','结束球局']:j?.stage==='idle'?['下一场']:j?.choices||[];
 if(['memory','name','proactive','shot_recording','driver','driver_kind','seven','seven_kind','miss'].includes(j?.stage||''))choices=[...choices,'先打球，稍后了解'];
 return <SafeAreaView style={{flex:1,backgroundColor:'#f1f5ee'}}><ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled"><Text style={styles.title}>电子球童 · 陪你完整打一场</Text><Text style={styles.note}>首次认识 → 赛前沟通 → 场中服务 → 回顾 → 下一场。可选凤凰山来源坐标演示或合成球场；GPS用按钮模拟，来源路径未作实地核验，原生语音仅限前台。操作日志用于恢复与审计，跨场档案由你选择。</Text>
 {!!error&&<Text accessibilityLiveRegion="polite" style={{color:'#a32b20'}}>{error}</Text>}
 {!client.current?<View style={styles.card}>{field('测试API地址',base,setBase)}{field('测试邮箱',email,setEmail)}{field('密码（至少10字符）',password,setPassword,true)}{button('注册并开始',()=>auth(true))}{button('登录并恢复',()=>auth(false))}</View>:speakerFirst?<View style={styles.card}><Text style={styles.heading}>第一步：让球童认出你的声音</Text><PrivateVoice profile={speaker} firstUse disabled={busy} beforeCapture={voice.stop} save={saveSpeaker} onUtterance={handleVoice}/></View>:<>
 <View style={styles.card}><Text style={styles.heading}>{stageLabels[j?.stage||'']||'加载中'}</Text>{transcript.slice(-16).map((t,i)=><Text key={i} style={styles.dialogue}>{t}</Text>)}{choices.map(t=>button(t,()=>t==='下一场'?submit('next_round'):say(t)))}{field('回答当前问题，或继续聊天',input,setInput)}{button('发送',async()=>{const text=input.trim();if(text){if(locale==='zh-CN')await say(text);else{log('你',text);await internationalSay(text);}setInput(current=>current===text?'':current);}})}{!speaker?.enabled&&<><Text style={styles.note}>语音语言 · 外语使用独立的多语言测试球局</Text>{voiceLocales.map(language=>button((locale===language?'✓ ':'')+language,()=>chooseLocale(language)))}{locale!=='zh-CN'&&button('重试多语言请求',async()=>{const current=international.current;if(current?.pending){const response=await current.retry();log('球童',response.result?.text||'');}})}</>}{!speaker?.enabled&&button(voice.enabled?'暂停语音':'开启前台语音',async()=>{if(voice.enabled)voice.stop();else await voice.start();})}{!speaker?.enabled&&<Text style={styles.note}>{voice.status}</Text>}<PrivateVoice profile={speaker} firstUse={false} disabled={busy} beforeCapture={voice.stop} save={saveSpeaker} onUtterance={handleVoice}/>{button('安静',()=>say('安静'))}</View>
 <View style={styles.card}><Text style={styles.heading}>这一场与我们的默契</Text><Text>{j?.round?`${j.round.id} · ${j.course_name||'合成球场'} · ${j.round.tee||'发球台未知'}`:'尚未开始球局'}</Text><Text>已确认{j?.score_summary.confirmed_holes||0}洞，小计{j?.score_summary.confirmed_subtotal??'未知'}杆</Text><Text>距离单位：{j?.distance_unit||'码'}</Text><Text>教练：{j?.coach.enabled?'已开启 · '+(j.coach.plan?.focus||'等待确认重点'):'关闭'}</Text><Text>{j?.memory_allowed?'跨场记住确认资料':j?.memory_allowed===false?'仅本场':'记忆意愿待确认'}</Text>
 {button('提交模拟发球台位置',()=>submit('gps',{data:j?.simulation?.positions.tee||{latitude:31,longitude:j?.round?.start_hole===2?121.0036:120.9992,accuracy_m:2}}),j?.stage!=='active')}{button('提交模拟设备位置',()=>submit('gps',{data:j?.simulation?.positions.fairway||{latitude:31,longitude:j?.round?.start_hole===2?121.005:121.001,accuracy_m:2}}),j?.stage!=='active')}{button('读取保存状态',async()=>{if(client.current)show(await client.current.snapshot());})}{button('重试原请求',async()=>{if(client.current){const sent=client.current.pending?.event?.text;show(await client.current.retry());if(sent)setInput(current=>current===sent?'':current);}},!client.current?.pending)}{button('关闭教练',()=>say('关闭教练'))}{button('下一场',()=>submit('next_round'),!['postgame','idle'].includes(j?.stage||''))}
 {button(showDetails?'收起测试记录':'高级：查看测试记录',async()=>setShowDetails(!showDetails))}{showDetails&&<Text selectable style={styles.note}>{JSON.stringify({profile:j?.profile,history:j?.history,coach:j?.coach},null,2)}</Text>}
 {button('退出',async()=>{voice.stop();if(client.current)await request(base,'/auth/logout',client.current.token,{});client.current=null;international.current=null;setLocale('zh-CN');speakerKey.current='';setSpeaker(null);setSpeakerFirst(false);setJ(null);setTranscript([]);})}</View></>}
 </ScrollView></SafeAreaView>;
}
export default function App(){return <SafeAreaProvider><Companion/></SafeAreaProvider>}
const styles=StyleSheet.create({page:{padding:20,maxWidth:850,width:'100%',alignSelf:'center'},title:{fontSize:26,fontWeight:'700',color:'#1d513b'},heading:{fontSize:18,fontWeight:'600',marginBottom:12,color:'#1d513b'},note:{fontSize:12,lineHeight:20,color:'#65796a',marginVertical:8},card:{padding:18,backgroundColor:'white',borderRadius:15,marginVertical:10},button:{padding:12,backgroundColor:'#215d43',borderRadius:9,marginVertical:5},input:{borderWidth:1,borderColor:'#d2dfcf',borderRadius:8,padding:12,marginVertical:6},dialogue:{fontSize:15,lineHeight:24,paddingVertical:6,color:'#294738'}});
