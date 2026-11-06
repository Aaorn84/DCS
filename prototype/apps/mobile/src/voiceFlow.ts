import type {Club, Score} from './domain';

export type VoiceFlow = {roundId: string; hole: number; phase: 'playing' | 'awaitingScore' | 'confirming' | 'finished'; draft: Score | null};
export type VoiceResult = {flow: VoiceFlow; text: string; handled: boolean; save?: {hole: number; score: Score}; pause?: boolean};
export const newFlow = (roundId: string, hole = 0): VoiceFlow => ({roundId, hole, phase: 'playing', draft: null});
const digits: Record<string, number> = {'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9};
function numeral(value: string): number {
  if (/^\d+$/.test(value)) return Number(value);
  if (value.includes('十')) {const [a,b]=value.split('十');return (a?digits[a]:1)*10+(b?digits[b]:0);}
  return digits[value] ?? NaN;
}
const num = '(\\d{1,2}|[一二两三四五六七八九]?十[一二三四五六七八九]?|[零一二两三四五六七八九])';
export function parseScore(input: string): Score | null {
  const normalized=input.replace(/\s/g,'');
  if (/[百千万负点小数]|\d+\.\d+/.test(normalized)) return null;
  const totalMatch=normalized.match(new RegExp(num+'杆'));
  if (!totalMatch) return null;
  const total=numeral(totalMatch[1]);
  const p=normalized.match(new RegExp(num+'(?:个)?罚(?:杆)?'));
  const t=normalized.match(new RegExp(num+'(?:个)?推(?:杆)?'));
  const penalty=p?numeral(p[1]):null; const putts=t?numeral(t[1]):null;
  if (!Number.isInteger(total) || total<1 || total>30 || (penalty??0)+(putts??0)>total) return null;
  return {total,penalty,putts};
}
export function scorePrompt(draft: Score): string {
  return `本洞${draft.total}杆${draft.penalty!==null?`，其中${draft.penalty}罚`:''}${draft.putts!==null?`，${draft.putts}推`:''}。确认记录吗？`;
}
export function voiceTurn(flow: VoiceFlow, input: string): VoiceResult {
  const clean=input.trim().replace(/[，。！？!?\s]/g,'');
  const result=(text:string, patch:Partial<VoiceFlow>={}, extra:Partial<VoiceResult>={}): VoiceResult => ({flow:{...flow,...patch},text,handled:true,...extra});
  if (/^(安静|先安静|停一下|暂停陪伴|暂停语音)$/.test(clean)) return result('好，需要时再叫我。',{}, {pause:true});
  if (flow.phase==='finished') return result('这场已经结束。可以在赛后记录里回顾。');
  if (/^(确认|确认保存|确认记录|对|对的|没错|是的|可以)$/.test(clean)) {
    if (flow.phase!=='confirming'||!flow.draft) return result('目前没有待确认的记录。');
    const save={hole:flow.hole,score:flow.draft};
    const finished=flow.hole===17;
    return result(finished?'已记下。这场结束了，辛苦了。':`已记下，接下来第${flow.hole+2}洞，需要时叫我。`,
      {hole:finished?17:flow.hole+1,phase:finished?'finished':'playing',draft:null},{save});
  }
  if (/^(跳过|先不记|现在不记|稍后记录|跳过记录)$/.test(clean) && flow.phase!=='playing') {
    const finished=flow.hole===17;
    return result('好，这洞先留空，不算成零杆。', {hole:finished?17:flow.hole+1,phase:finished?'finished':'playing',draft:null});
  }
  if (/^(不对|取消|重新说|重新记录)$/.test(clean) && flow.phase==='confirming') return result('好，这洞一共几杆？',{phase:'awaitingScore',draft:null});
  const ended=/(这洞|本洞|这一洞).*(打完|结束|完成)|^(打完这洞了|下一洞|球洞结束)$/.test(clean);
  if (flow.phase!=='playing' || ended) {
    const draft=parseScore(clean);
    if (draft) return result(scorePrompt(draft),{phase:'confirming',draft});
    if (ended) {
      if (flow.phase==='confirming'&&flow.draft) return result('刚才的记录还没确认，可以说确认、重新说，或先不记。');
      if (flow.phase==='awaitingScore') return result('等你方便时告诉我，或者说先不记。');
      return result('这洞一共几杆？',{phase:'awaitingScore'});
    }
    if (/杆|罚|推/.test(clean)) return result('这次没有听清总杆，请说“六杆”这样的数字。');
  }
  return {flow,text:'',handled:false};
}

// Distance facts are user-provided; no map, lie, wind or safety is inferred.
export function distanceAdvice(input: string, clubs: Club[]): string | null {
  const match=input.match(/(?:还剩|剩下|距离|目标|还有|剩)\s*(\d{1,3}(?:\.\d+)?)\s*(米|码)/);
  if (!match) return null;
  const target=Number(match[1])*(match[2]==='码'?0.9144:1);
  if (target<=0||target>400) return '这个距离超出当前短句建议范围，请再确认一下距离。';
  const carry=clubs.filter(c=>c.distanceType==='carry').sort((a,b)=>Math.abs(a.distance-target)-Math.abs(b.distance-target)).slice(0,2);
  if (!carry.length) return '听到了你的距离。还没有确认过的球杆落地距离，可以先告诉我常用球杆打多远吗？';
  const choices=carry.map(c=>`${c.name}自报落地${c.distance}米，${c.distance>=target?'比目标多':'比目标少'}${Math.abs(c.distance-target).toFixed(0)}米`).join('；');
  return `按你说的距离和已存球包：${choices}。还没考虑球位、风和障碍，只作距离参考。`;
}
