"""Versioned, language-neutral gateway to the existing journey reducer.
Bounded fixture NLU is deliberately not a production multilingual model.
"""
import copy
import hashlib
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from round_state import require, canonical

LOCALES = ('zh-CN', 'en-US', 'en-GB', 'ja-JP', 'ko-KR',
           'es-ES', 'pt-PT', 'de-DE', 'fr-FR', 'it-IT')
MARKETS = ('US', 'EEA', 'UK', 'JP', 'KR')
EVENT_TYPES = ('fact_request', 'player_intent', 'decision_commitment', 'execution_report',
               'shot_outcome', 'feel_or_cause', 'correction', 'score_report',
               'state_transition', 'interaction_override', 'companion_dialogue',
               'profile_answer', 'confirmation')
DEFAULTS = dict(locale='zh-CN', market_region='US', distance_unit='yd', temperature_unit='C',
                wind_unit='m/s', timezone='UTC', data_region=None)
# Speech status catalogue is also consumed by the native client adapter.
MESSAGES = {
 'zh-CN': {'clarify':'这句话我还不能确定意思，请换一种说法。', 'translation_required':'这段回复还没有经过当前语言适配，已保留处理结果。', 'configured':'语言与地区设置已保存。'},
 'en-US': {'clarify':'I’m not sure what you mean. Could you rephrase that?', 'translation_required':'The result is saved, but this reply is not available in your language yet.', 'configured':'Language and regional preferences saved.'},
 'en-GB': {'clarify':'I’m not sure what you mean. Could you rephrase that?', 'translation_required':'The result is saved, but this reply is not available in your language yet.', 'configured':'Language and regional preferences saved.'},
 'ja-JP': {'clarify':'意味を確認できませんでした。別の言い方で教えてもらえますか？', 'translation_required':'処理結果は保存しましたが、この返答はまだ日本語に対応していません。', 'configured':'言語と地域の設定を保存しました。'},
 'ko-KR': {'clarify':'뜻을 정확히 이해하지 못했어요. 다르게 말씀해 주시겠어요?', 'translation_required':'처리 결과는 저장했지만 이 답변은 아직 한국어로 제공되지 않습니다.', 'configured':'언어와 지역 설정을 저장했어요.'}}

MESSAGES.update({
 'es-ES': {'clarify': 'No entendí bien. ¿Puedes decirlo de otra forma?', 'translation_required': 'El resultado está guardado. La respuesta aún no está disponible en español.', 'configured': 'Preferencias de idioma y región guardadas.'},
 'pt-PT': {'clarify': 'Não percebi bem. Podes dizer de outra forma?', 'translation_required': 'O resultado foi guardado. A resposta ainda não está disponível em português.', 'configured': 'Preferências de idioma e região guardadas.'},
 'de-DE': {'clarify': 'Das habe ich nicht ganz verstanden. Kannst du es anders formulieren?', 'translation_required': 'Das Ergebnis ist gespeichert. Die Antwort ist noch nicht auf Deutsch verfügbar.', 'configured': 'Sprach- und Regionseinstellungen gespeichert.'},
 'fr-FR': {'clarify': 'Je n’ai pas bien compris. Peux-tu reformuler ?', 'translation_required': 'Le résultat est enregistré. La réponse n’est pas encore disponible en français.', 'configured': 'Préférences de langue et de région enregistrées.'},
 'it-IT': {'clarify': 'Non ho capito bene. Puoi dirlo in un altro modo?', 'translation_required': 'Il risultato è salvato. La risposta non è ancora disponibile in italiano.', 'configured': 'Preferenze di lingua e regione salvate.'},
})

def config(value, previous=None):
 require(isinstance(value,dict), 'regional configuration must be an object')
 require(not set(value)-set(DEFAULTS), 'unknown regional configuration field')
 c={**DEFAULTS, **(previous or {}), **value}
 require(c['locale'] in LOCALES, 'unsupported locale; no silent language fallback')
 require(c['market_region'] in MARKETS, 'unsupported market region')
 require(c['distance_unit'] in ('yd','m') and c['temperature_unit'] in ('C','F') and c['wind_unit'] in ('m/s','mph','km/h'), 'invalid units')
 require(c['data_region'] is None or c['data_region'] in ('US','EEA','UK','JP','KR'), 'invalid data region')
 try:ZoneInfo(c['timezone'])
 except (ZoneInfoNotFoundError,TypeError,ValueError):raise ValueError('invalid IANA timezone')
 return c

def number(n,low,high):
 require(type(n) in (int,float) and math.isfinite(n) and low<=n<=high,'invalid numeric value')
 return n

def club(v):
 require(isinstance(v,str) and bool(re.fullmatch(r'driver|[3-9]w|[2-9]i|[2-9]h|pw|sw|lw|gw|putter',v)), 'invalid canonical club')
 return v

def validate_candidate(c):
 require(isinstance(c,dict) and not set(c)-{'type','slots','confidence','alternatives'},'invalid candidate envelope')
 require(c.get('type') in EVENT_TYPES,'unsupported semantic event')
 require(isinstance(c.get('slots',{}),dict),'slots must be an object')
 number(c.get('confidence',1),0,1)
 for a in c.get('alternatives',[]):
  require(isinstance(a,dict) and a.get('type') in EVENT_TYPES and isinstance(a.get('slots',{}),dict),'invalid alternative')
 return copy.deepcopy(c)

def impact(c):
 """Different material interpretations are never selected just by ASR confidence."""
 material={'player_intent','decision_commitment','execution_report','shot_outcome','correction','score_report','state_transition','interaction_override','profile_answer','confirmation'}
 base=(c['type'],canonical(c.get('slots',{})))
 for a in c.get('alternatives',[]):
  if (a['type'],canonical(a.get('slots',{})))!=base:
   if a['type'] in material or c['type'] in material or a.get('slots')!=c.get('slots'):return 'high'
 return 'low'

# Explicit samples only. Unrecognised input stays unknown and never enters Chinese NLU.
PHRASES={
 'zh': {'还有多少':'distance','还剩多少':'distance','多少':'distance','多远':'distance','距离':'distance','这杆怎么打':'strategy','怎么打':'strategy','应该怎么打':'strategy','可以':'yes','好':'yes','没有':'zero_penalties','没有罚杆':'zero_penalties','两推':'two_putts','确认记录':'confirm_score','开始球局':'start','结束球局':'finish','确认结束':'finish_confirm','关闭教练':'coach_off'},
 'en': {'how far':'distance','how far is it':'distance','what do you recommend':'strategy','how should i play this':'strategy','yes':'yes','ok':'yes','no':'no','start round':'start','finish round':'finish','confirm finish':'finish_confirm','skip onboarding':'skip','no penalties':'zero_penalties','two putts':'two_putts','confirm score':'confirm_score','no coaching':'coach_off'},
 'ja': {'あと何ヤード':'distance','残り距離は':'distance','どう打てばいい':'strategy','はい':'yes','いいえ':'no','ラウンド開始':'start','ラウンド終了':'finish','終了を確認':'finish_confirm','初期設定をスキップ':'skip','ペナルティなし':'zero_penalties','2パット':'two_putts','スコアを確定':'confirm_score','コーチ機能をオフ':'coach_off'},
 'ko': {'얼마 남았어':'distance','남은 거리는':'distance','어떻게 치면 좋을까':'strategy','네':'yes','아니요':'no','라운드 시작':'start','라운드 종료':'finish','종료 확인':'finish_confirm','초기 설정 건너뛰기':'skip','벌타 없음':'zero_penalties','2퍼트':'two_putts','스코어 확정':'confirm_score','코치 기능 끄기':'coach_off'}}
PHRASES.update({
 'es': {'cuánto falta': 'distance', 'cómo juego este golpe': 'strategy', 'sí': 'yes', 'no': 'no', 'empezar la vuelta': 'start', 'terminar la vuelta': 'finish', 'confirmar el final': 'finish_confirm', 'omitir la configuración inicial': 'skip', 'sin penalizaciones': 'zero_penalties', 'dos putts': 'two_putts', 'confirmar la tarjeta': 'confirm_score', 'desactivar el entrenador': 'coach_off'},
 'pt': {'quanto falta': 'distance', 'como devo jogar esta tacada': 'strategy', 'sim': 'yes', 'não': 'no', 'iniciar a volta': 'start', 'terminar a volta': 'finish', 'confirmar o fim': 'finish_confirm', 'saltar a configuração inicial': 'skip', 'sem penalizações': 'zero_penalties', 'dois putts': 'two_putts', 'confirmar o cartão': 'confirm_score', 'desativar o treinador': 'coach_off'},
 'de': {'wie weit ist es noch': 'distance', 'wie soll ich diesen schlag spielen': 'strategy', 'ja': 'yes', 'nein': 'no', 'runde starten': 'start', 'runde beenden': 'finish', 'rundenende bestätigen': 'finish_confirm', 'einrichtung überspringen': 'skip', 'keine strafschläge': 'zero_penalties', 'zwei putts': 'two_putts', 'score bestätigen': 'confirm_score', 'coaching ausschalten': 'coach_off'},
 'fr': {'quelle distance reste-t-il': 'distance', 'comment jouer ce coup': 'strategy', 'oui': 'yes', 'non': 'no', 'commencer la partie': 'start', 'terminer la partie': 'finish', 'confirmer la fin': 'finish_confirm', 'passer la configuration initiale': 'skip', 'sans pénalité': 'zero_penalties', 'deux putts': 'two_putts', 'confirmer le score': 'confirm_score', 'désactiver le coaching': 'coach_off'},
 'it': {'quanto manca': 'distance', 'come gioco questo colpo': 'strategy', 'sì': 'yes', 'no': 'no', 'inizia il giro': 'start', 'termina il giro': 'finish', 'conferma la fine': 'finish_confirm', 'salta la configurazione iniziale': 'skip', 'nessuna penalità': 'zero_penalties', 'due putt': 'two_putts', 'conferma il punteggio': 'confirm_score', 'disattiva il coaching': 'coach_off'},
})

EUROPEAN_CLUB_PATTERNS = {'es': 'usé (?:el )?hierro (?:del )?([2-9])', 'pt': 'usei (?:o )?ferro ([2-9])', 'de': 'ich habe (?:mit )?(?:dem )?([2-9])er-eisen gespielt', 'fr': 'j\\x27ai utilisé (?:le )?fer ([2-9])', 'it': 'ho usato (?:il )?ferro ([2-9])'}
EUROPEAN_SCORE_PATTERNS = {'es': '(\\d{1,2}) golpes', 'pt': '(\\d{1,2}) tacadas', 'de': '(\\d{1,2}) schläge', 'fr': '(\\d{1,2}) coups', 'it': '(\\d{1,2}) colpi'}
ACTIONS={
 'distance':('fact_request',{'domain':'distance'}), 'strategy':('fact_request',{'domain':'strategy'}),
 'yes':('confirmation',{'value':True}), 'no':('confirmation',{'value':False}),
 'start':('state_transition',{'action':'start'}), 'finish':('state_transition',{'action':'finish'}),
 'finish_confirm':('state_transition',{'action':'finish_confirm'}), 'skip':('state_transition',{'action':'skip_onboarding'}),
 'zero_penalties':('score_report',{'penalties':0}), 'two_putts':('score_report',{'putts':2}),
 'confirm_score':('confirmation',{'action':'score'}), 'coach_off':('interaction_override',{'coaching':False})}

def parse_fixture(text,locale):
 require(isinstance(text,str) and 0<len(text)<=1000,'invalid utterance')
 require(locale in LOCALES,'unsupported locale')
 t=text.strip().lower().strip('¿¡').rstrip('?.!？。！').rstrip().replace('’', "'")
 action=PHRASES.get(locale[:2],{}).get(t)
 if action:
  kind,slots=ACTIONS[action];return dict(type=kind,slots=copy.deepcopy(slots),confidence=1)
 # Numeric answers are meaningful only with a live question; core retains ownership.
 if re.fullmatch(r'\d{1,3}',t):return dict(type='profile_answer',slots={'number':int(t)},confidence=1)
 patterns={'en':r'(?:i used|used) ([2-9])(?: iron|i)', 'ja':r'([2-9])番アイアンを使った', 'ko':r'([2-9])번 아이언을 쳤어', **EUROPEAN_CLUB_PATTERNS}
 m=re.fullmatch(patterns.get(locale[:2],r'(?!)'),t)
 if m:return dict(type='execution_report',slots={'club':m[1]+'i'},confidence=1)
 patterns={'en':r'(\d{1,2}) strokes', 'ja':r'(\d{1,2})打', 'ko':r'(\d{1,2})타', **EUROPEAN_SCORE_PATTERNS}
 m=re.fullmatch(patterns.get(locale[:2],r'(?!)'),t)
 if m:return dict(type='score_report',slots={'total':int(m[1])},confidence=1)
 return None

def canonical_message(c):
 """Compatibility renderer, not the public semantic protocol. Reject unused slots."""
 kind=c['type'];v=c.get('slots',{})
 allowed={
 'fact_request':{'domain'},'confirmation':{'value','action'},'state_transition':{'action'},
 'interaction_override':{'coaching','quiet'},'profile_answer':{'number','course','tee','name','memory','proactive','shot_recording','miss','goal','condition'},
 'score_report':{'total','putts','penalties','hole'},'player_intent':{'approach'},
 'decision_commitment':{'club'},'execution_report':{'club'}}
 require(kind in allowed,'semantic type requires attribution adapter; not silently committed')
 require(not set(v)-allowed[kind],'unsupported semantic slots')
 if kind=='fact_request':
  require(v.get('domain') in ('distance','strategy','previous_distance'),'unsupported fact domain')
  return {'distance':'还有多少','strategy':'这杆怎么打','previous_distance':'上一杆打了多少'}[v['domain']]
 if kind=='confirmation':
  require(len(v)==1,'confirmation must have one meaning')
  if 'action' in v:
   require(v['action']=='score','unsupported confirmation');return '确认记录'
  require(type(v.get('value')) is bool,'boolean confirmation required');return '可以' if v['value'] else '不可以'
 if kind=='state_transition':
  actions={'start':'开始球局','finish':'结束球局','finish_confirm':'确认结束','skip_onboarding':'先打球','next_round':'下一场','close':'今天到这里'}
  require(v.get('action') in actions,'unsupported transition');return actions[v['action']]
 if kind=='interaction_override':
  require(len(v)==1 and all(type(x) is bool for x in v.values()),'one boolean override required')
  if 'coaching' in v:
   require(v['coaching'] is False,'coaching opt-in needs full consent flow');return '关闭教练'
  return '安静' if v['quiet'] else '继续'
 if kind=='profile_answer':
  require(len(v)==1,'one answer per turn')
  if 'number' in v:
   require(type(v['number']) is int,'integer answer required');return str(number(v['number'],0,999))
  key=next(iter(v),None)
  if key in ('memory','proactive','shot_recording'):
   require(type(v[key]) is bool,'boolean preference required')
   return {'memory':('可以记住','仅本场'),'proactive':('可以提醒','不主动提醒'),'shot_recording':('可以记录','不记录击球')}[key][0 if v[key] else 1]
  enums={'miss':{'right':'偏右','left':'偏左','short':'打短','variable':'不固定'},
         'goal':{'relax':'轻松打球','score':'争取成绩','practice':'练一个重点'},
         'condition':{'good':'状态不错','tired':'有些疲劳','relax':'只想放松'}}
  if key in enums:
   require(v[key] in enums[key],'invalid profile enum');return enums[key][v[key]]
  if key=='course':
   require(v[key] in ('synthetic-demo','dongguan-phoenix-ab-blue-demo'),'course provider not connected')
   return '演示球场（合成）' if v[key]=='synthetic-demo' else '东莞凤凰山（A+B蓝台演示）'
  if key=='tee':
   require(v[key] in ('blue','white','red'),'unsupported tee');return {'blue':'蓝台','white':'白台','red':'红台'}[v[key]]
  require(key=='name' and isinstance(v[key],str) and 0<len(v[key])<=30,'invalid profile answer');return v[key]
 if kind=='score_report':
  require(bool(v) and any(k in v for k in ('total','putts','penalties')),'empty score')
  for k,n in v.items():require(type(n) is int and (1 if k in ('total','hole') else 0)<=n<=(18 if k=='hole' else 30),'invalid score')
  require('hole' not in v or 'total' in v,'hole requires total')
  require('total' not in v or v.get('putts',0)+v.get('penalties',0)<=v['total'],'invalid score sum')
  prefix=(str(v['hole'])+'号洞' if 'hole' in v else '这洞') if 'total' in v else ''
  return prefix+'，'.join(str(v[k])+{'total':'杆','putts':'推','penalties':'罚杆'}[k] for k in ('total','putts','penalties') if k in v)
 if kind=='player_intent':
  require(v.get('approach') in ('conservative','attack'),'invalid approach');return '稳一点' if v['approach']=='conservative' else '争取进攻'
 name=club(v.get('club'));label={'driver':'一号木','pw':'P杆','sw':'S杆','lw':'高抛杆','gw':'挖起杆','putter':'推杆'}.get(name)
 if label is None:label=name[:-1]+{'i':'铁','w':'号木','h':'混合杆'}[name[-1]]
 return ('我还是用了' if kind=='execution_report' else '我想用')+label

def snapshot(s):
 from journey import view
 return {'configuration':copy.deepcopy(s.get('international',{}).get('configuration',DEFAULTS)),
         'journey':view(s), 'capabilities':{'semantic_protocol':4,'nlu':'bounded-fixtures',
         'reply_localization':'partial','production_ready':False,'overseas_course_provider':False,
         'regional_storage_enforced':False},'version':s['version']}

def reduce_event(s,p,seq,now):
 if p.get('protocol_version')==1:
  from international_legacy import reduce_event as legacy
  return legacy(s,p,seq,now)
 require(p.get('protocol_version') in (2,3,4),'unsupported international protocol')
 require(not set(p)-{'protocol_version','event_id','observed_at','type','configuration','candidate','text','data'},'unknown event field')
 eid=p.get('event_id');require(isinstance(eid,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',eid)),'invalid event id')
 require(isinstance(p.get('observed_at'),str),'observation time required')
 try:stamp=datetime.fromisoformat(p['observed_at'].replace('Z','+00:00'));require(stamp.tzinfo is not None,'timezone required')
 except (KeyError,TypeError,ValueError):raise ValueError('invalid observation time')
 i=s.setdefault('international',{'configuration':config({}),'receipts':{}})
 digest=hashlib.sha256(canonical(p).encode()).hexdigest()
 if eid in i['receipts']:
  require(i['receipts'][eid]==digest,'event id reused with different payload')
  return {'text':'','speak_allowed':False,'duplicate':True}
 cfg=i['configuration'];kind=p.get('type');result={}
 if kind=='configure':
  require(set(p)<={'protocol_version','event_id','observed_at','type','configuration'},'invalid configure fields')
  cfg=config(p.get('configuration'),cfg);i['configuration']=cfg
  result={'text':MESSAGES[cfg['locale']]['configured'],'status':'configured','speak_allowed':True}
 else:
  require(kind in ('semantic','utterance','resume','gps'),'unsupported international input')
  c=validate_candidate(p.get('candidate')) if kind=='semantic' else parse_fixture(p.get('text'),cfg['locale']) if kind=='utterance' else None
  if kind in ('semantic','utterance') and (c is None or impact(c)=='high' or c.get('confidence',1)<.8):
   result={'text':MESSAGES[cfg['locale']]['clarify'],'status':'clarify','speak_allowed':True,'candidate':c}
  else:
   from journey import reduce_journey
   event={'protocol_version':{2:32,3:65,4:87}[p['protocol_version']],'event_id':'intl_'+hashlib.sha256(eid.encode()).hexdigest()[:40],'observed_at':p['observed_at'],'type':kind if kind in ('gps','resume') else 'message'}
   if c:
    # Typed profile answers cannot answer another pending question or act as controls.
    if c['type']=='profile_answer':
     v=c.get('slots',{});key=next(iter(v),None);j=s.get('journey',{});stage=j.get('stage','memory')
     stages={'memory':('memory',),'name':('name',),'proactive':('proactive',),'shot_recording':('shot_recording',),
             'course':('course',),'tee':('tee',),'miss':('miss',),'goal':('goal',),'condition':('condition',)}
     if key in stages:require(stage in stages[key],'profile answer does not own current question')
     if key=='number':require(stage in ('driver','seven','start_hole') or (stage=='active' and (j.get('consultation') or {}).get('phase') in ('tee_club','approach_club')),'number has no live ability or starting-hole question')
     if key=='name':require(not re.search(r'安静|结束|确认|跳过|撤销|继续|可以|不可以|开始|球局',str(v[key])),'name conflicts with control grammar')
    event['text']=canonical_message(c)
   if kind=='gps':
    require(isinstance(p.get('data'),dict),'GPS data required');event['data']=copy.deepcopy(p['data'])
   # Unit preferences are explicit and independent of market/language.
   if s.get('journey'):
    s['journey'].setdefault('profile',{})['units']={'value':'米' if cfg['distance_unit']=='m' else '码','source':'regional_configuration'}
   out=reduce_journey(s,event,seq,now)
   source=out.get('text','')
   native=cfg['locale']=='zh-CN'
   # Never speak untranslated Chinese using a Japanese/Korean/English voice.
   result={**out,'source_text':source,'text':source if native or not source else MESSAGES[cfg['locale']]['translation_required'],
           'speak_allowed':bool(out.get('speak_allowed')) and native,
           'status':'processed' if native or not source else 'translation_required','semantic_event':c}
 from round_state import fact_value
 if s.get('journey',{}).get('quiet') or any(fact_value(s,k) is True for k in ('context.quiet','context.preparing')):
  result={**result,'text':'','speak_allowed':False}
 i['receipts'][eid]=digest
 return result
