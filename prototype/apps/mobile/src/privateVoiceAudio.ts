import {File,Paths} from 'expo-file-system';
import {digest,CryptoDigestAlgorithm} from 'expo-crypto';
import {ExpoSpeechRecognitionModule as Recognition} from 'expo-speech-recognition';
import {createSpeakerEmbeddingExtractor} from 'expo-sherpa-onnx';

const modelName='3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx';
const modelUrl='https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/'+modelName;
const modelSize=28281164;
const modelSHA256='aa3cfc16963a10586a9393f5035d6d6b57e98d358b347f80c2a30bf4f00ceba2';
let verifiedUri:string|undefined;
async function intact(file:File){
  if(!file.exists||file.size!==modelSize)return false;
  const hash=new Uint8Array(await digest(CryptoDigestAlgorithm.SHA256,await file.bytes()));
  return Array.from(hash,v=>v.toString(16).padStart(2,'0')).join('')===modelSHA256;
}
let provision:Promise<string>|undefined;
function localFilePath(uri:string){
  // Android's java.io.File.toURI() emits file:/path; iOS uses file:///path.
  return uri.startsWith('file:/')?decodeURIComponent(uri.replace(/^file:\/+/, '/')):uri;
}
function localFileUri(uri:string){
  return uri.replace(/^file:\/+/, 'file:///');
}
export function deleteClip(uri:string) {
  const f=new File(localFileUri(uri));
  if(f.exists)f.delete();
}
function modelPath(){
  if(provision)return provision;
  provision=(async()=>{
    const model=new File(Paths.cache,modelName);
    if(model.exists&&(model.uri!==verifiedUri||model.size!==modelSize)&&!(await intact(model)))model.delete();
    if(!model.exists){
      const part=new File(Paths.cache,modelName+'.part');
      if(part.exists)part.delete();
      try{
        await File.downloadFileAsync(modelUrl,part);
        if(!(await intact(part)))throw new Error('声纹模型校验失败，请重试。');
        await part.move(model);
      }finally{const leftover=new File(Paths.cache,modelName+'.part');if(leftover.exists)leftover.delete();}
    }
    verifiedUri=model.uri;
    return localFilePath(model.uri);
  })().finally(()=>{provision=undefined;});
  return provision;
}
export async function extractSpeaker(uri:string){
  const engine=await createSpeakerEmbeddingExtractor({model:await modelPath(),numThreads:2,provider:'cpu'});
  try{return await engine.computeEmbeddingFromFile(localFilePath(uri));}
  finally{await engine.destroy();}
}
export function transcribeVerifiedClip(uri:string,signal:AbortSignal){
  if(signal.aborted)return Promise.resolve('');
  if(!Recognition.supportsOnDeviceRecognition())throw new Error('未安装可用的离线语音识别，请使用文字输入。');
  return new Promise<string>((resolve,reject)=>{
    let done=false;
    const finish=(text:string,error?:Error)=>{
      if(done)return;done=true;
      clearTimeout(timer);result.remove();end.remove();failed.remove();
      signal.removeEventListener('abort',cancel);
      Recognition.abort();
      if(error)reject(error);else resolve(text);
    };
    const cancel=()=>finish('');
    const result=Recognition.addListener('result',event=>{if(event.isFinal)finish(event.results[0]?.transcript??'');});
    const end=Recognition.addListener('end',()=>finish(''));
    const failed=Recognition.addListener('error',event=>finish('',event.error==='no-speech'||event.error==='aborted'?undefined:new Error('离线语音识别未完成，可使用文字输入。')));
    const timer=setTimeout(()=>finish('',new Error('离线语音识别超时。')),15000);
    signal.addEventListener('abort',cancel,{once:true});
    try{Recognition.start({lang:'zh-CN',interimResults:false,continuous:false,requiresOnDeviceRecognition:true,
      audioSource:{uri:localFileUri(uri)},recordingOptions:{persist:false}});}
    catch(e){finish('',e instanceof Error?e:new Error('无法启动离线语音识别。'));}
  });
}
