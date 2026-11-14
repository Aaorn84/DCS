import React,{useEffect,useRef,useState} from 'react';
import {AppState,Platform,Pressable,Text,View} from 'react-native';
import {useAudioRecorder} from '@siteed/audio-studio';
import {Directory,Paths} from 'expo-file-system';
import * as Speech from 'expo-speech';
import {ExpoSpeechRecognitionModule as Recognition} from 'expo-speech-recognition';
import type {PrivateVoiceProps} from './PrivateVoice';
import {enroll,enrollmentCount,minimumEnrollmentMs,verifyThenTranscribe} from './speakerGate';
import {deleteClip,extractSpeaker,transcribeVerifiedClip} from './privateVoiceAudio';

const clipCache=()=>new Directory(Paths.cache,'caddie-private-voice');
const phrases=['你好小鸟，今天我想轻松打一场球。','这杆还有多少码？我想瞄向球道中间。','这一洞打了五杆，其中两推。'];
export default function PrivateVoice({profile,firstUse,disabled,beforeCapture,save,onUtterance}:PrivateVoiceProps) {
  const recorder=useAudioRecorder();
  const latest=useRef(recorder);latest.current=recorder;
  const [editing,setEditing]=useState(false),[recording,setRecording]=useState(false);
  const [working,setWorking]=useState(false),[step,setStep]=useState(0),[status,setStatus]=useState('');
  const samples=useRef<number[][]>([]);
  const inFlight=useRef(false),capturing=useRef(false),alive=useRef(true);
  const session=useRef(new AbortController());
  const timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const enrolling=firstUse||editing;
  const supported=Platform.OS==='ios'||(Platform.OS==='android'&&Number(Platform.Version)>=33);
  const remove=(uri:string)=>{try{deleteClip(uri);}catch{/* best-effort cache cleanup */}};
  function abort(){
    session.current.abort();clearTimeout(timer.current);
    if(capturing.current){
      capturing.current=false;
      void latest.current.stopRecording().then(r=>{if(r?.fileUri)remove(r.fileUri);},()=>{});
    }
    if(alive.current){setRecording(false);setStatus('');}
  }
  useEffect(()=>{
    alive.current=true;
    const cache=clipCache();
    try{if(cache.exists)cache.delete();}catch{/* retry deletion when this clip completes */}
    const app=AppState.addEventListener('change',state=>{if(state!=='active')abort();});
    return ()=>{alive.current=false;abort();app.remove();};
  },[]);
  async function finish(){
    if(!capturing.current||inFlight.current)return;
    clearTimeout(timer.current);capturing.current=false;setRecording(false);setStatus('');
    const signal=session.current.signal;
    const current=()=>!signal.aborted&&alive.current;
    inFlight.current=true;setWorking(true);
    let uri='';
    try{
      const clip=await latest.current.stopRecording();uri=clip.fileUri;
      if(!current())return;
      if(enrolling){
        if(clip.durationMs<minimumEnrollmentMs){setStatus('请完整读完这句话，再结束录音。');return;}
        const vector=await extractSpeaker(uri);
        if(!current())return;
        samples.current.push(vector);
        if(samples.current.length<enrollmentCount){setStep(samples.current.length);setStatus('');return;}
        const template=enroll(samples.current);samples.current=[];setStep(0);
        if(!template){setStatus('三段声音差异较大，请在安静处重新录入。');return;}
        await save({enabled:true,template});setEditing(false);setStatus('已开启“只听我的声音”。');
      }else if(profile?.enabled){
        const text=await verifyThenTranscribe({profile,durationMs:clip.durationMs,isCurrent:current,
          embedding:()=>extractSpeaker(uri),transcribe:()=>transcribeVerifiedClip(uri,signal)});
        if(!text||!current())return;
        const reply=await onUtterance(text);
        if(current()&&reply.text)Speech.speak(reply.text,{language:'zh-CN'});
      }
    }catch(e){if(current())setStatus(e instanceof Error?e.message:'无法完成语音，请使用文字。');}
    finally{if(uri)remove(uri);inFlight.current=false;if(alive.current)setWorking(false);}
  }
  async function start(){
    if(inFlight.current||capturing.current||!supported)return;
    inFlight.current=true;setWorking(true);setStatus('正在检查麦克风权限…');
    session.current=new AbortController();const signal=session.current.signal;
    try{
      if(!firstUse)beforeCapture();
      const mic=await Recognition.getMicrophonePermissionsAsync();
      if(!mic.granted&&!(await Recognition.requestMicrophonePermissionsAsync()).granted)throw new Error('请允许麦克风访问，或继续使用文字。');
      if(!enrolling&&Platform.OS==='ios'){
        const permission=await Recognition.requestPermissionsAsync();
        if(!permission.granted)throw new Error('未开启离线语音权限，可使用文字。');
      }
      if(signal.aborted){setStatus('录音启动已中断，回到应用后请再试。');return;}
      setStatus('正在启动麦克风…');
      const cache=clipCache();cache.create({idempotent:true});
      await latest.current.startRecording({sampleRate:16000,channels:1,encoding:'pcm_16bit',
        outputDirectory:cache.uri,enableProcessing:false,showNotification:false,autoResumeAfterInterruption:false});
      if(signal.aborted){
        const r=await latest.current.stopRecording();remove(r.fileUri);return;
      }
      capturing.current=true;setRecording(true);setStatus('正在录音，请读完这句话后点结束。');timer.current=setTimeout(()=>void finish(),7000);
    }catch(e){if(!signal.aborted)setStatus(e instanceof Error?e.message:'无法开启录音。');}
    finally{inFlight.current=false;if(alive.current)setWorking(false);}
  }
  async function setProfile(next:Parameters<PrivateVoiceProps['save']>[0]){
    if(inFlight.current||capturing.current)return;
    inFlight.current=true;setWorking(true);
    try{await save(next);samples.current=[];setStep(0);setEditing(false);setStatus('');}
    catch(e){setStatus(e instanceof Error?e.message:'无法保存声纹设置。');}
    finally{inFlight.current=false;if(alive.current)setWorking(false);}
  }
  const unavailable=disabled||working;
  const button=(label:string,fn:()=>void,locked=false)=><Pressable accessibilityRole="button" disabled={unavailable||locked}
    onPress={fn} style={{padding:10,marginVertical:4,backgroundColor:unavailable||locked?'#e8ece7':'#d6eadc',borderRadius:8}}><Text>{label}</Text></Pressable>;
  return <View style={{paddingVertical:10}}>
    <Text style={{fontWeight:'700'}}>只听我的声音{profile?.enabled?' · 已开启':''}</Text>
    {enrolling&&<Text>可选录入 3 段声音。首次会下载端侧模型；录音用完删除，声纹模板只保存在本机。</Text>}
    {!supported&&<Text>当前设备不支持此开发版的声纹模式，可继续用文字。</Text>}
    {enrolling&&supported&&<Text>第 {step+1}/3 段：{phrases[step]}</Text>}
    {(enrolling||profile?.enabled)&&supported&&button(recording?'结束录音':enrolling?'录下这句话':'说一句（验证声纹）',()=>void (recording?finish():start()))}
    {firstUse?button('跳过声纹录入',()=>void setProfile({enabled:false}),recording):
      <>{supported&&button(enrolling?'取消录入':profile?.template?'重新录入声纹':'录入声纹',
        ()=>{samples.current=[];setStep(0);setEditing(!editing);setStatus('');},recording)}
      {profile?.template&&!enrolling&&button(profile.enabled?'关闭声纹模式':'开启声纹模式',
        ()=>void setProfile({...profile,enabled:!profile.enabled}),recording)}
      {profile?.template&&button('删除本机声纹',()=>void setProfile({enabled:false}),recording)}</>}
    {!!status&&<Text accessibilityLiveRegion="polite">{status}</Text>}
  </View>;
}
