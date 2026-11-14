import React from 'react';
import {Pressable,Text,View} from 'react-native';
import type {SpeakerProfile} from './speakerGate';
import type {SpokenReply} from './useVoice';
export type PrivateVoiceProps={
  profile:SpeakerProfile|null;
  firstUse:boolean;
  disabled:boolean;
  beforeCapture:()=>void;
  save:(profile:SpeakerProfile)=>Promise<void>;
  onUtterance:(text:string)=>Promise<SpokenReply>;
};
export default function PrivateVoice({firstUse,save,profile,disabled}:PrivateVoiceProps){
  if(!firstUse&&!profile?.enabled)return null;
  return <View><Text>声纹录入需要手机原生开发版，网页可继续用文字。</Text>
    <Pressable disabled={disabled} accessibilityRole="button" onPress={()=>void save({enabled:false})}>
      <Text>{firstUse?'跳过声纹录入':'关闭声纹模式'}</Text>
    </Pressable></View>;
}
