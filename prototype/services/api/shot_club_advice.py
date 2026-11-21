"""Concrete clubs for short-game advice, without inventing shot distances."""
import re

def recommendation(profile,*,target_yards=None,purpose='pitch',lie=None,unit='码'):
    uses=profile.get('lofted_wedge_uses',{}).get('value',{})
    if lie=='沙坑':
        sand=[str(n) for n,use in uses.items() if use=='沙坑']
        loft=min(sand,key=lambda n:abs(int(n)-58)) if sand else '58'
        basis='按你注明的沙坑用途，' if sand else ''
        return basis+f'可考虑{loft}度杆先出沙；坑沿高或球埋沙时，以脱困和可控落点为先，按熟悉的挥幅打，不套用全挥Carry。'
    if target_yards is not None:
        from tee_strategy import layup_club_text
        return layup_club_text(profile,target_yards,unit).replace('过渡用杆','这杆用杆').replace('过渡落点','目标落点')
    desired=('切滚','切滚球') if purpose=='chip' else ('抛切','短切','脱困')
    preferred=[str(n) for n,use in uses.items() if use in desired]
    if preferred:
        club=min(preferred,key=int)+'度杆'
        return f'按你注明的球杆用途，可考虑{club}；落点距离尚未确认，先选看得见的宽处，再按熟悉的挥幅控制。'
    ranges=profile.get('lofted_wedge_ranges',{}).get('value',{})
    wedges=[str(n) for n,v in ranges.items() if v.get('high',0)>0 and uses.get(str(n))!='沙坑']
    if purpose=='chip':
        club='P杆'
    elif wedges:
        club=min(wedges,key=lambda n:abs(int(n)-52))+'度杆'
    else:
        return '当前缺少适合抛切或脱困的球杆用途和短距离控制资料，请告诉我你常用哪支挖起杆；先确认可用落点，不直接套用长杆距离。'
    return f'这杆可考虑{club}，用你熟悉的'+('切滚' if purpose=='chip' else '短挥幅')+'；先确认落点及滚动空间，不能把全挥Carry当作本次短切距离。'

def supplement(state,text,*,lie=None,target_yards=None):
    if not text or re.search(r'[？?]',text):return text
    if re.search(r'(?:[2-9二三四五六七八九]号?铁|[Pp]杆|\d{2}度杆|一号木|[135]号木|推杆)',text):return text
    if not re.search(r'切滚|抛切|脱困|切回|挖起杆|沙杆|先出沙',text):return text
    profile=state.get('journey',{}).get('profile',{})
    unit=profile.get('units',{}).get('value','码')
    # An explicit Carry target is a landing distance, not pin or total distance.
    match=re.search(r'Carry(?:先瞄)?(?:约)?(\d+)(?:[–—~到-](\d+))?(码|米)',text)
    if target_yards is None and match:
        value=(int(match[1])+int(match[2]))/2 if match[2] else int(match[1])
        target_yards=value/(.9144 if match[3]=='米' else 1)
    purpose='chip' if '切滚' in text and not re.search(r'别.*切滚|不建议.*切滚|不.*切滚',text) else 'pitch'
    return text+recommendation(profile,target_yards=target_yards,purpose=purpose,lie=lie,unit=unit)
