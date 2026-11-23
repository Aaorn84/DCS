import React,{useEffect,useState} from 'react';
import {View,Text,Pressable,StyleSheet} from 'react-native';
import type {CourseLibrary,SetupDraft} from './courseLibrary';
import {bag} from '../../../shared/core/bag';
import {setupProfile} from '../../../shared/core/offlineSetup';
import {setupPrompt,setupChoices} from './localSetup';
type Props={library:CourseLibrary;state:Awaited<ReturnType<CourseLibrary['read']>>;busy:boolean;answer:(text:string)=>Promise<unknown>;refresh:()=>Promise<unknown>;download:(id:string,tee:string)=>Promise<unknown>;remove:(id:string,tee:string)=>Promise<unknown>;open:(id:string)=>Promise<unknown>;start:()=>Promise<unknown>;run:(fn:()=>Promise<unknown>)=>void};
export default function OfflineSetupPanel(p:Props){
 const button=(label:string,fn:()=>Promise<unknown>)=><Pressable key={label} accessibilityRole="button" disabled={p.busy} onPress={()=>p.run(fn)} style={styles.button}><Text style={{color:'white'}}>{label}</Text></Pressable>;
 const draft=p.state.draft;const [profile,setProfile]=useState<any>({});
 useEffect(()=>{let active=true;void p.library.profilePreview().then(value=>{if(active)setProfile(value);}).catch(()=>{if(active)setProfile({});});return()=>{active=false;};},[p.library,p.state]);
 return <View style={styles.card}><Text style={styles.title}>本机资料与球场下载</Text><Text>{setupPrompt(draft)}</Text>
 {setupChoices(draft).map(label=>button(label,()=>p.answer(label)))}
 {button(draft.memory_allowed?'改为仅本场':'允许跨场记住',()=>p.answer(draft.memory_allowed?'关闭跨场记忆':'允许跨场记忆'))}
 {button('先选球场，稍后补资料',()=>p.answer('先打球'))}
 <Text style={styles.title}>本机球杆Carry</Text>{bag(profile).map(c=><Text key={c.label}>{c.label} · {c.low===c.high?c.high:c.low+'–'+c.high}码{c.estimated?'（暂估）':''}</Text>)}<Text>可一次报多支，例如“3号木210码，5号木200码”。</Text>
 <Text style={styles.title}>已下载球场</Text>
 {!p.state.downloads.length&&<Text>还没有完整下载的球场；首次下载需要联网。</Text>}
 {p.state.downloads.map(d=><View key={d.course_id+d.tee}><Text>{d.name} · {d.tee} · 已下载</Text>{button('选择 '+d.name,()=>p.answer(d.name))}{button('删除下载 '+d.name,()=>p.remove(d.course_id,d.tee))}</View>)}
 {draft.stage==='tee'&&p.state.downloads.filter(d=>d.course_id===draft.course_id).map(d=>button(d.tee,()=>p.answer(d.tee)))}
 {draft.stage==='ready'&&button('开始本机球局（无需网络）',p.start)}
 <Text style={styles.title}>下载管理</Text>{button('联网刷新球场目录',p.refresh)}
 {p.state.catalog.map(c=><View key={c.course_id}><Text>{c.name} · {c.holes}洞{c.reference_simulation?' · 演示数据':''}</Text>{c.tees.map((tee:string)=>button('下载或更新 '+c.name+' '+tee,()=>p.download(c.course_id,tee)))}</View>)}
 <Text>下载完成并校验后才能离线开局；规则与策略引擎随APP提供。语音模型需另行准备。</Text>
 {!!p.state.rounds.length&&<><Text style={styles.title}>本机球局</Text>{p.state.rounds.map(r=>button((r.phase==='preparing'?'恢复开局 ':'打开球局 ')+r.spec.round.tee+' · '+r.id.slice(0,8),()=>p.open(r.id)))}</>}
 </View>;
}
const styles=StyleSheet.create({card:{backgroundColor:'white',padding:16,borderRadius:14,gap:10},title:{fontSize:18,fontWeight:'600'},button:{backgroundColor:'#215d43',padding:12,borderRadius:8,marginVertical:4}});
