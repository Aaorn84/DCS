"""Optional, scoped post-shot prompts driven by local audio candidates."""
import re
from round_state import canonical
from shot_links import scope

def handle(state, event, now):
    journey = state['journey']
    audio = journey.setdefault('shot_audio', {'enabled': True, 'phase': 'idle'})
    text = event.get('text', '').strip()
    if text in ('关闭击球声音识别', '开启击球声音识别'):
        enabled=text.startswith('开启')
        ready=(audio.get('scope') == canonical(scope(state)) and now-audio.get('armed_at',0)<=600 and bool(audio.get('arm_id')))
        if (enabled and event.get('protocol_version',0)>=111 and ready
                and audio.get('detected_arm_id')==audio.get('arm_id')):
            from ball_rules import plan_shot
            plan_shot(state,event)
            # Explicit re-enable starts another detection session, never another
            # copy of the consumed club decision.
            audio.update(arm_id=event['event_id'],armed_at=now,club=None,delay_seconds=5,
                         asked_at=-100000,asked_arm_id=None)
        audio.update(enabled=enabled, phase='armed' if enabled and ready else 'idle')
        if enabled and not ready and event.get('protocol_version',0)>=111:
            return '已开启声音识别开关，但尚未进入待击球状态。请先确认这杆用杆和方案。'
        return '已'+('开启' if audio['enabled'] else '关闭')+'击球声音识别。'
    waiting_answer=(audio.get('phase')=='asked' and audio.get('scope')==canonical(scope(state))
                    and 0<=now-audio.get('asked_at',audio.get('detected_at',0))<=600)
    if waiting_answer:
        clean=re.sub(r'[，,。！!？?\s]','',text)
        clean=re.sub(r'^(?:看到了|看到球了|我看到了|看见了|看见球了)', '', clean)
        landing=re.fullmatch(r'(?:球|落在|球在|在|打到|落到)?(球道|长草|沙坑|果岭)(中间|中央|左侧|右侧|左边|右边|上|里)?(?:了)?',clean)
        if landing:
            if event.get('protocol_version',0)>=111:
                from ball_rules import confirm_normal_shot
                confirm_normal_shot(state,event,now)
            from lie_position import fresh_position
            pos=fresh_position(state,now)
            journey['reported_landing']={
                'scope':canonical(scope(state)), 'lie':landing[1], 'side':landing[2],
                'text':text, 'event_id':event['event_id'], 'at':now,
                'position':pos['value'] if pos else None}
            audio['phase']='idle'
            return '记下了，球在'+landing[1]+(landing[2] or '')+'。到球旁需要建议时问我。'
        if clean in ('在','球在','球在的','找到了','看到球了'):
            if event.get('protocol_version',0)>=111:
                from ball_rules import confirm_normal_shot
                confirm_normal_shot(state,event,now)
            audio['phase']='idle'
            return '好，到了球旁需要建议时叫我。'
    if text not in ('音频检测到疑似击球', '击球声音等待结束'):
        if text and audio.get('phase') == 'waiting':
            audio['phase'] = 'idle'
        return None
    if not audio.get('enabled') or audio.get('scope') != canonical(scope(state)) or now-audio.get('armed_at', 0)>600:
        return ''
    if text == '音频检测到疑似击球':
        if audio.get('phase') == 'armed':
            if event.get('protocol_version',0)>=110:
                from ball_rules import note_shot
                note_shot(state,event,now)
            audio.update(phase='waiting', detected_at=now, detected_arm_id=audio.get('arm_id'))
        return ''
    if audio.get('phase') != 'waiting' or now-audio['detected_at'] < audio['delay_seconds']:
        return ''
    audio['phase'] = 'idle'
    if journey.get('quiet') or state.get('session', {}).get('draft'):
        return ''
    from ball_outcome import current
    from ball_rules import current as rule_current, blocking
    if blocking(state) or (not rule_current(state) and (current(state) or {}).get('phase') not in (None,'closed')):
        return ''
    audio.update(phase='asked', enabled=False, asked_at=now, asked_arm_id=audio.get('arm_id'))
    return '看到球落哪儿了吗？' if audio.get('risk_or_unknown') else '球在吗？'

def arm(state, event, now):
    journey = state['journey']
    audio = journey.setdefault('shot_audio', {'enabled': True, 'phase': 'idle'})
    last = journey.get('last_consultation') or {}
    decision = (journey.get('player_decisions') or [{}])[-1]
    selected = decision.get('event_id') == event['event_id']
    selected = selected or bool(last.get('decision') and last.get('selected_club') and last.get('audio_armed_event') != last.get('decision'))
    if not selected:
        return
    if event.get('protocol_version',0)>=111:
        from ball_rules import plan_shot
        plan_shot(state,event)
    last['audio_armed_event'] = last.get('decision')
    club = decision.get('club') if decision.get('event_id') == event['event_id'] else last.get('selected_club', {}).get('label', '')
    # Broad, positively verified landing zones qualify for the shortest question.
    options=(last.get('last_offer') or {}).get('options', [])
    zones=[option.get('zone', {}) for option in options if option.get('club')==club]
    broad=bool(zones) and all(z.get('width_yards', 0)>=35 and not z.get('hazards') for z in zones)
    audio.update(phase='armed' if audio.get('enabled') else 'idle', scope=canonical(scope(state)), arm_id=event['event_id'],
                 armed_at=now, club=club, delay_seconds=5 if re.search(r'挖起|沙杆|度杆|P杆|推杆', club or '') else 10,
                 risk_or_unknown=not broad)
