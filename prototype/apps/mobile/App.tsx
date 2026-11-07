import React, {useRef, useState} from 'react';
import {Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View} from 'react-native';
import {SafeAreaProvider, SafeAreaView} from 'react-native-safe-area-context';
import * as Crypto from 'expo-crypto';
import {request} from './src/api';
import {RoundSession, SessionSnapshot} from './src/roundSession';
import {syntheticCourse} from './src/syntheticCourse';
import {useVoice} from './src/useVoice';

/** Separate integration build; the existing companion app remains unchanged. */
function Lab() {
 const [base,setBase]=useState(Platform.OS==='android'?'http://10.0.2.2:8787':'http://localhost:8787');
 const [email,setEmail]=useState('');const [password,setPassword]=useState('');
 const [token,setToken]=useState('');const [roundId,setRoundId]=useState('test-round');
 const [ready,setReady]=useState(false);const [snapshot,setSnapshot]=useState<SessionSnapshot|null>(null);
 const [message,setMessage]=useState('');const [reply,setReply]=useState('');const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);const lock=useRef(false);
 const [course,setCourse]=useState(JSON.stringify(syntheticCourse,null,2));
 const [gps,setGPS]=useState('{"latitude":31,"longitude":121.001,"accuracy_m":2}');
 const client=()=>new RoundSession(base,token,roundId);
 const voice=useVoice(async text=>{
  if(lock.current)throw new Error('正在处理上一条事件');lock.current=true;setBusy(true);
  try{const r=await sendVoice(text);return {text:r.result.speak_allowed?r.result.text:'',pause:r.result.pause||!r.result.speak_allowed};}
  finally{lock.current=false;setBusy(false);}
 });
 async function run(job:()=>Promise<void>) {
  if(lock.current)return;lock.current=true;setBusy(true);setError('');
  try{await job();}catch(e){setError(e instanceof Error?e.message:'请求失败');}finally{lock.current=false;setBusy(false);}
 }
 async function login(register:boolean) {
  voice.stop();
  const result=await request(base,register?'/auth/register':'/auth/login',undefined,{email,password});
  setToken(result.token);setPassword('');setReady(false);setSnapshot(null);setReply('已登录。请创建或恢复测试球局。');
 }
 async function sendVoice(text:string) {
  if(!ready||!token)throw new Error('请先登录并创建或恢复球局。');
  const r=await client().submit(Crypto.randomUUID(),{type:'voice',event_id:Crypto.randomUUID(),observed_at:new Date().toISOString(),text});
  setSnapshot(r.state);setReply(r.result.text||'已接收，本次不主动发声。');return r;
 }
 const button=(title:string,action:()=>void,disabled=false)=><Pressable accessibilityRole="button" disabled={busy||disabled} onPress={action} style={[s.button,(busy||disabled)&&{opacity:.4}]}><Text style={s.white}>{title}</Text></Pressable>;
 const input=(label:string,value:string,onChangeText:(t:string)=>void,secret=false,multiline=false)=><View><Text style={s.label}>{label}</Text><TextInput accessibilityLabel={label} value={value} onChangeText={onChangeText} secureTextEntry={secret} multiline={multiline} editable={!busy} autoCapitalize="none" style={[s.input,multiline&&{minHeight:90}]}/></View>;
 return <SafeAreaView style={{flex:1,backgroundColor:'#f4f5ef'}}><ScrollView contentContainerStyle={s.page}>
  <Text style={s.title}>电子球童 · 三路输入联调</Text>
  <Text style={s.body}>语音说明行为与结果，GPS提供位置，球场说明这里有什么。熟悉你的能力与偏好需要几场球，可能五场或更多；今天先依据可靠信息帮你记录和问距。</Text>
  <Text style={s.note}>独立开发原型；预填地图与定位均为合成数据。无真实球场、后台GPS或锁屏验证。这里只做状态闭环，不提供选杆或过水保证。</Text>
  {!!error&&<Text accessibilityLiveRegion="polite" style={s.error}>{error}</Text>}
  <View style={s.card}><Text style={s.heading}>1 · 测试账号与球局</Text>
   {input('本地API地址',base,t=>{voice.stop();setReady(false);setToken('');setBase(t);})}
   {input('测试邮箱',email,setEmail)}{input('测试密码（至少10字符）',password,setPassword,true)}
   {button('注册测试账号',()=>void run(()=>login(true)))}{button('登录',()=>void run(()=>login(false)))}
   {input('球局ID（同账号同ID可恢复）',roundId,t=>{voice.stop();setReady(false);setRoundId(t);})}
   {button('创建 / 恢复球局',()=>void run(async()=>{const r=await client().create();setSnapshot(r.state);setReady(true);}),!token)}
   {token&&button('退出并清除本次登录',()=>void run(async()=>{voice.stop();try{await request(base,'/auth/logout',token,{});}finally{setToken('');setReady(false);setSnapshot(null);}}))}
  </View>
  <View style={s.card}><Text style={s.heading}>2 · 球场与GPS事件</Text>
   {input('球场快照JSON（预填为合成样本）',course,setCourse,false,true)}
   {button('提交球场快照',()=>void run(async()=>{voice.stop();const r=await client().submit(Crypto.randomUUID(),{type:'course',event_id:Crypto.randomUUID(),observed_at:new Date().toISOString(),data:JSON.parse(course)});setSnapshot(r.state);setReply('球场快照已加载。');}),!ready)}
   {input('定位JSON（设备位置，不自动等于球位）',gps,setGPS,false,true)}
   {button('提交定位样本',()=>void run(async()=>{voice.stop();const r=await client().submit(Crypto.randomUUID(),{type:'gps',event_id:Crypto.randomUUID(),observed_at:new Date().toISOString(),data:JSON.parse(gps)});setSnapshot(r.state);setReply('定位样本已提交；未推断击球。');}),!ready)}
  </View>
  <View style={s.card}><Text style={s.heading}>3 · 语音 / 转写联调</Text>
   <Text style={s.body}>依次说：还有多少米 → 这洞六杆 → 两推 → 没有罚杆 → 确认。需要时可说：撤销上一条记分、安静、继续。每次只补问一项。</Text>
   <Text style={s.note}>原生开发版可使用前台识别；Web仅提交转写文本，不请求麦克风。当前简化语法不等于通用语义理解。</Text>
   {input('语音转写备用输入',message,setMessage)}
   {button('提交这一句',()=>void run(async()=>{await sendVoice(message);setMessage('');}),!ready||!message.trim())}
   {button(voice.enabled?'暂停前台语音':'开启前台语音',()=>{if(voice.enabled)voice.stop();else void voice.start();},!ready)}
   <Text style={s.note}>{voice.status}</Text><Text accessibilityLiveRegion="polite" style={s.body}>{reply}</Text>
  </View>
  <View style={s.card}><Text style={s.heading}>4 · 查看确认事实与重放</Text>
   {button('读取持久化状态',()=>void run(async()=>{const r=await client().snapshot();setSnapshot(r.state);}),!ready)}
   <Text selectable style={s.code}>{JSON.stringify(snapshot,null,2)}</Text>
   <Text style={s.note}>只在“确认”提交成功后记分。本状态账本与旧/sync记分分开，勿重复保存同一洞。测试凭证只留在本次内存。</Text>
  </View>
 </ScrollView></SafeAreaView>;
}
export default function App(){return <SafeAreaProvider><Lab/></SafeAreaProvider>;}
const s=StyleSheet.create({page:{padding:20,maxWidth:800,width:'100%',alignSelf:'center'},title:{fontSize:27,fontWeight:'700',color:'#174c3c',marginBottom:14},heading:{fontSize:19,fontWeight:'600',color:'#174c3c',marginBottom:12},body:{fontSize:15,lineHeight:24,color:'#33473a',marginVertical:7},note:{fontSize:12,lineHeight:20,color:'#6c786b',marginVertical:8},card:{padding:18,backgroundColor:'white',borderRadius:16,marginVertical:12},label:{fontSize:12,color:'#5d6e62',marginTop:12},input:{padding:12,borderWidth:1,borderColor:'#d5dfd0',borderRadius:8,marginVertical:7,color:'#263b2e'},button:{padding:14,backgroundColor:'#174c3c',borderRadius:8,marginVertical:6},white:{color:'white',textAlign:'center'},error:{color:'#9a2525',padding:14,backgroundColor:'#ffebe4'},code:{fontSize:11,color:'#425344',marginTop:12}});
