import {useEffect, useRef, useState} from 'react';
import {AppState, Platform} from 'react-native';
import * as Speech from 'expo-speech';
import {ExpoSpeechRecognitionModule as Recognition} from 'expo-speech-recognition';

export type SpokenReply={text:string;pause?:boolean};
/** Foreground voice loop. Explicitly pauses on background; no false lock-screen claim. */
export function useVoice(onUtterance:(text:string)=>Promise<SpokenReply>) {
  const [status,setStatus]=useState('尚未开启语音');
  const [enabled,setEnabled]=useState(false);
  const [transcript,setTranscript]=useState('');
  const handler=useRef(onUtterance);handler.current=onUtterance;
  const active=useRef(false);const processing=useRef(false);const received=useRef(false);
  const generation=useRef(0);
  function stop() {
    active.current=false;generation.current++;setEnabled(false);
    Recognition.abort();void Speech.stop();setStatus('语音已暂停');
  }
  function listen() {
    if(!active.current||AppState.currentState!=='active')return;
    received.current=false;setStatus('正在听你说');
    Recognition.start({lang:'zh-CN',interimResults:true,continuous:false,
      contextualStrings:['七号铁','这洞打完了','六杆','两推','一罚','确认','先不记'],
      recordingOptions:{persist:false}});
  }
  async function speak(text:string, resume=true) {
    const current=generation.current;
    received.current=true;Recognition.abort();await Speech.stop();
    if(!active.current||current!==generation.current)return;
    setStatus('球伴正在回应');
    await new Promise<void>((resolve,reject)=>Speech.speak(text,{language:'zh-CN',rate:0.95,
      onDone:()=>resolve(),onStopped:()=>resolve(),onError:()=>reject(new Error('语音播报不可用'))}));
    if(active.current&&current===generation.current) {
      if(resume)listen();else stop();
    }
  }
  async function start() {
    try {
      if(Platform.OS==='web')throw new Error('网页仅预览流程；请用原生开发版验证麦克风和语音。');
      if(!Recognition.isRecognitionAvailable())throw new Error('设备语音识别不可用，请使用文字备用入口。');
      const permission=await Recognition.requestPermissionsAsync();
      if(!permission.granted)throw new Error('未获得麦克风或语音识别权限，可使用文字备用入口。');
      active.current=true;generation.current++;setEnabled(true);listen();
    } catch(e) {active.current=false;setEnabled(false);setStatus(e instanceof Error?e.message:'语音暂不可用');}
  }
  useEffect(()=>{
    const result=Recognition.addListener('result',(event)=>{
      const text=event.results[0]?.transcript??'';setTranscript(text);
      if(!event.isFinal||!text.trim()||!active.current||processing.current||received.current)return;
      received.current=true;processing.current=true;Recognition.abort();setStatus('正在理解');
      const current=generation.current;
      void (async()=>{
        try {
          const response=await handler.current(text);
          if(current!==generation.current||!active.current)return;
          if(response.text)await speak(response.text,!response.pause);
          else if(response.pause)stop();else listen();
        } catch {stop();setStatus('这次语音交互未完成，记录保持原状，请重试。');}
        finally {processing.current=false;}
      })();
    });
    const end=Recognition.addListener('end',()=>{
      if(active.current&&!received.current&&!processing.current) {
        active.current=false;setEnabled(false);setStatus('本轮聆听已结束，重新开启可继续；锁屏待真机验证。');
      }
    });
    const error=Recognition.addListener('error',(event)=>{
      if(event.error==='aborted'||!active.current)return;
      active.current=false;setEnabled(false);generation.current++;void Speech.stop();
      setStatus(event.error==='no-speech'?'没有听清，重新开启即可；不会自动记录。':'语音识别中断，可重新开启；文字仍可使用。');
    });
    const app=AppState.addEventListener('change',(next)=>{
      if(next!=='active'&&active.current){stop();setStatus('已转入后台，当前开发版暂停语音；锁屏会话尚待原生验证。');}
    });
    return ()=>{active.current=false;generation.current++;Recognition.abort();void Speech.stop();result.remove();end.remove();error.remove();app.remove();};
  },[]);
  return {status,enabled,transcript,start,stop,speak};
}
