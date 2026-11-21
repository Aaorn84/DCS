"""Read-only named-club tee feasibility; never a player commitment."""
import re,math
from club_selection import selection

def parse(text):
    clean=re.sub(r'[\s，,。！!？?]','',text)
    match=re.fullmatch(r'(?:用)?(一号木|1号木|三号木|3号木|五号木|5号木|[2-9]号铁|铁木杆)(?:开球)?(?:可以|能|能不能|可不可以)(?:过沙坑?|飞过沙坑?|越过沙坑?|飞越沙坑?|打过沙坑?|开球|打)?(?:吗|么|呢)?',clean)
    if not match:return None
    return selection(match[1],hybrid=True,expanded=True)

def handle(state,text,now):
    text_query=text
    chosen=parse(text)
    if not chosen:return None
    from tee_strategy import analyze,suggest,crossing_text,aiming_text
    from tee_geometry import tee_targets
    analysis=analyze(state,now)
    if not analysis:return '先更新发球台位置，我再按这支杆的Carry核对落区和过沙距离；刚才讨论的方案保留。'
    if analysis['par'] not in (4,5):return None
    club=analysis['clubs'].get(chosen['key'])
    if not club:return '还没有'+chosen['label']+'的已知Carry，请报这支杆的落地距离，我再核对过沙余量和落区。'
    targets=tee_targets(state,analysis,[(chosen['key'],club)],allow_crossing=True)
    if not targets:return chosen['label']+'目前没有匹配到已核对的球道落点。不能只按Carry判断可用；请确认落区、障碍远沿和现场边界，再比较路线。'
    target=max(targets,key=lambda row:row['width_m'])
    unit=state['journey'].get('profile',{}).get('units',{}).get('value','码');scale=.9144 if unit=='米' else 1
    carry=round(club['carry_yards']*scale);width=round(target['width_m']/(1 if unit=='米' else .9144))
    text=f"可以把{chosen['label']}作为开球候选：Carry约{carry}{unit}，瞄{aiming_text(target,unit)}，落区横向约{width}{unit}。"
    text+=crossing_text(target,unit)
    if target.get('crossing_m') is not None:
        reserve=club['carry_yards']*scale-target['crossing_m']/(1 if unit=='米' else .9144)
        text+=f'按已知Carry，比这条线的障碍远沿多约{round(reserve)}{unit}；现场再确认风、触球和飞越余量。'
    elif re.search(r'过沙|越.*沙',text_query):
        evidence=bunker_clearance(state,analysis,target,club['carry_yards'],unit)
        text+=evidence or '当前地图还不能唯一核对你所指沙坑的远沿，请确认是哪处沙坑，再判断飞越余量。'
    return text


def bunker_clearance(state,a,target,carry,unit,*,distance_only=False):
    from tee_geometry import mapped_polygons
    from round_state import fact_value
    origin=fact_value(state,'context.device_position')
    course=state.get('evidence',{}).get(a.get('course_evidence'),{}).get('data',{})
    hole=next((h for h in course.get('holes',[]) if h['number']==a.get('hole')),None)
    reference=target.get('reference') or {}
    if not origin or not hole or reference.get('distance_m') is None:return None
    rows=[]
    for rings in mapped_polygons(hole,course.get('reference_simulation') is True)['bunker'].values():
        coords=[((lon-origin['longitude'])*111195*math.cos(math.radians(origin['latitude'])),(lat-origin['latitude'])*111195) for lon,lat in rings[0]]
        if not coords:continue
        center=math.hypot(sum(x for x,y in coords)/len(coords),sum(y for x,y in coords)/len(coords))
        rows.append((abs(center-reference['distance_m']),max(math.hypot(x,y) for x,y in coords)))
    rows.sort()
    if not rows or rows[0][0]>15 or (len(rows)>1 and rows[1][0]-rows[0][0]<5):return None
    if distance_only:return rows[0][1]
    far=rows[0][1];div=1 if unit=='米' else .9144;margin=carry*.9144-far
    answer=f'所指沙坑远沿距当前球位直线约{round(far/div)}{unit}。'
    if margin<=0:return answer+f'已知Carry比远沿短约{round(-margin/div)}{unit}，不宜按正常Carry安排飞越。'
    answer+=f'按常态Carry算，越过远沿约有{round(margin/div)}{unit}余量。'
    answer+=('余量较小，考虑击球偏差和风，不能保证过沙；可继续走沙坑旁的球道路线，或比较沙前方案。' if margin<15*.9144 else '距离上可列为飞越候选，仍需按风和触球情况确认。')
    return answer+'这是到沙坑远沿的直线距离；当前瞄准线走沙坑旁，不代表实际必须飞越。'
