"""Explicitly reported unplayable balls, wrong balls, whiffs and common free relief."""
import re

from lie_position import infer
from round_state import fact_value


AREAS={'一般区域':'general','球道':'general','长草':'general','沙坑':'bunker',
       '果岭':'green','发球区':'tee','发球台':'tee','罚杆区':'penalty'}
CAUSES={'unplayable','free_relief','wrong_ball','swing_intent','moved_ball'}


def options(row):
    phase=row['phase']
    if phase.endswith('_area'):
        return ['一般区域','沙坑','果岭','发球区','罚杆区']
    if phase=='unplayable_option':
        result=['回上一杆位置','后延线救济','侧向两杆救济']
        if row.get('area')=='bunker':
            result.append('沙坑外后延线救济')
        return result
    if phase=='unplayable_reference':
        return ['已确认原球位置','找不到原球位置']
    if phase=='free_option':
        result=['区内免罚救济']+([] if row.get('no_play_zone') else ['放弃救济原位打'])
        if row.get('area')=='bunker':
            result.append('沙坑外后延线救济')
        return result
    if phase=='free_interference':
        return ['影响球位、站姿或挥杆','只影响击球线路','不清楚']
    if phase=='wrong_ball_location':
        return ['洞中打了别人的球','仅在发球区换球开球']
    if phase=='wrong_ball_target':
        return ['刚才记录的这一杆打错球','错球击球尚未记录']
    if phase=='wrong_ball_format':
        return ['比杆赛','比洞赛']
    if phase=='wrong_ball_return':
        return ['已回原球位置']
    if phase=='swing_intent':
        return ['有意击球但挥空','只是练习挥杆']
    if phase=='move_circumstance':
        return ['寻找辨认时意外碰动','普通意外碰动','故意移动','不清楚']
    if phase=='move_natural':
        return ['已在果岭放回或救济后跨区域','都不是','不清楚']
    if phase=='move_replace':
        return ['已放回原位置']
    return None


def start(state,flow,event,now,cause):
    from ball_rules import incident
    row=incident(state,flow,event,now,cause,capture=False)
    row['cause']=cause
    return row


def area_prompt(row):
    row['phase']=row['cause']+'_area'
    return '球目前在一般区域、沙坑、果岭、发球区，还是罚杆区？'


def choose_area(state,flow,row,area):
    from ball_rules import water_options
    row['area']=area
    if row['cause'] in ('unplayable','free_relief') and area=='penalty':
        row.update(cause='water',phase='water_color')
        return '罚杆区内按规则17处理，先确认红桩或黄桩。'+water_options(state,row)
    if row['cause']=='unplayable':
        if area=='tee':
            from ball_rules import close_incident
            close_incident(flow,row)
            return '球仍在发球区内时可按规则6.2重新选择位置或架球，已保留原有击球，未追加不可打球罚杆。'
        row['phase']='unplayable_option'
        return '由你决定是否按不可打球处理。通常可罚一杆回上一杆位置、从原球位置后延线或两杆范围侧向救济。'+('沙坑内的后延线、侧向救济要留在该沙坑；也可罚两杆在沙坑外后延线救济。' if area=='bunker' else '')
    if row['cause']=='free_relief':
        row['phase']='free_interference'
        return '这处修理地或临时积水影响球位、站姿或挥杆，还是只影响击球线路？'
    if row['cause']=='moved_ball':
        flow['balls'][flow['active_ball']]['inside_penalty_area']=area=='penalty'
        row['phase']='move_circumstance'
        return '是在寻找辨认时意外碰动、普通意外碰动，还是故意移动？'
    return None


def replace_prompt(flow,row,amount):
    from ball_rules import add_penalty
    if amount:
        add_penalty(flow,row,amount,suffix='movement')
    row['phase']='move_replace'
    return ('罚一杆，' if amount else '这次免罚，')+'将球放回原位置，不确定时合理估计。放回后说“已放回原位置”。'


def finish_restoring(state,flow,row,event,now):
    from ball_rules import close_incident,position
    from shot_links import add
    from lie_position import fresh_position
    pos=fresh_position(state,now)
    if pos:
        state['journey']['shot_location_candidates']=[
            item for item in state['journey'].get('shot_location_candidates',[])
            if [item['round_id'],item['course'],item['hole']]!=flow['scope']]
        add(state,position(state,now),pos['evidence_ids'],'restored_original_position')
    flow.pop('open_shot',None)
    close_incident(flow,row)
    return '已确认原球位置，位置恢复未计作击球，可以继续讨论下一杆。'


def handle(state,flow,event,text,now):
    from ball_rules import pending,close_incident,position,add_stroke,last_stroke,add_penalty,finish_relief
    row=pending(flow)
    if not row:
        if text in ('这球不可打','不可打球','宣布不可打','这球打不了'):
            row=start(state,flow,event,now,'unplayable')
            if flow['balls'][flow['active_ball']].get('inside_penalty_area'):
                return choose_area(state,flow,row,'penalty')
            return area_prompt(row)
        if text in ('球在修理地','临时积水影响击球','需要免罚救济','球在临时积水里'):
            row=start(state,flow,event,now,'free_relief')
            if flow['balls'][flow['active_ball']].get('inside_penalty_area'):
                return choose_area(state,flow,row,'penalty')
            return area_prompt(row)
        if text in ('打错球了','刚才打错球','打了别人的球'):
            row=start(state,flow,event,now,'wrong_ball')
            row['phase']='wrong_ball_location'
            return '是在洞中打了别人的球，还是仅在发球区换球开球？'
        if text in ('挥空了','没打到球','刚才挥空'):
            row=start(state,flow,event,now,'swing_intent')
            row['phase']='swing_intent'
            return '是有意击球但挥空，还是只是练习挥杆？'
        if text in ('球被我碰动了','我把球碰动了','寻找时碰动球','球被别人碰动了','球自己动了','风把球吹动了'):
            row=start(state,flow,event,now,'moved_ball')
            if text=='球被别人碰动了':
                return replace_prompt(flow,row,0)
            if text=='寻找时碰动球':
                return replace_prompt(flow,row,0)
            if text in ('球自己动了','风把球吹动了'):
                row['phase']='move_natural'
                return '球是否已在果岭标记拿起并放回，或在救济后停稳又被自然力量移到另一球场区域、界外？'
            return area_prompt(row)
        return None
    if row['cause'] not in CAUSES:
        return None
    if row['cause']=='free_relief' and '禁止打球区' in text:
        row['no_play_zone']=True
        return '已记录禁止打球区的强制救济，请继续选择完全救济点和救济方式。'
    if text in AREAS and row['phase'].endswith('_area'):
        return choose_area(state,flow,row,AREAS[text])
    if row['phase']=='unplayable_option':
        choices={'回上一杆位置':('stroke_distance',1),'后延线救济':('back_on_line',1),
                 '侧向两杆救济':('lateral',1),'沙坑外后延线救济':('back_on_line',2)}
        if text in choices:
            option,amount=choices[text]
            if amount==2 and row['area']!='bunker':
                return '沙坑外两杆罚杆后延线选项仅适用于沙坑不可打球。'
            row.update(option=option,relief_penalty_amount=amount,penalty_suffix='unplayable',
                       outside_bunker=amount==2)
            if option=='stroke_distance':
                row['phase']='replay'
                return '已选罚一杆回上一杆位置；到原位完成规定的重打准备后报告球位。'
            row['phase']='unplayable_reference'
            return '请确认原球的具体位置。树上球的侧向救济参考点为球正下方地面点；找不到原球位置时可选回上一杆位置。'
    if row['phase']=='unplayable_reference':
        if text=='找不到原球位置':
            row['phase']='unplayable_option'
            return '原球位置未知时，选回上一杆位置的一杆加距离救济。'
        if text=='已确认原球位置':
            row['phase']='drop'
            restriction='球必须留在原沙坑。' if row['area']=='bunker' and not row.get('outside_bunker') else ''
            return ('已确认参考点。'+('保持原球位置在球洞与抛球点之间后退抛球。' if row['option']=='back_on_line'
                    else '在原球位置两杆范围内侧向抛球，不更靠洞。')+restriction+'由本人从膝盖高度正确抛球，确认球停在规定救济区。')
    if row['phase']=='free_interference':
        if text=='只影响击球线路' and row['area']!='green':
            close_incident(flow,row)
            return '一般区域或沙坑仅线路受影响通常不适用这项免罚救济，继续按当前球位打。'
        if text=='不清楚':
            return '先现场确认是否存在规则16的实际妨碍，或请裁判协助确认后再选救济。'
        if text in ('影响球位、站姿或挥杆','只影响击球线路'):
            row['phase']='free_option'
            return '可取不更靠洞的最近完全救济点。'+('沙坑内无完全救济点时可用最大可用救济点；留在沙坑可免罚，沙坑外后延线救济罚一杆。' if row['area']=='bunker' else '一般区域的一杆范围须留在一般区域；果岭上按规定放置。')
    if row['phase']=='free_option':
        if text=='放弃救济原位打':
            if row.get('no_play_zone'):
                return '已确认禁止打球区，需要完成规定救济后再打。'
            close_incident(flow,row)
            return '已选择原位打，未增加罚杆。'
        if text in ('区内免罚救济','沙坑外后延线救济'):
            if text=='沙坑外后延线救济' and row['area']!='bunker':
                return '这个选项需要球在沙坑中。'
            amount=1 if text=='沙坑外后延线救济' else 0
            row.update(relief_penalty_amount=amount,penalty_suffix='abnormal_condition',
                       option='back_on_line' if amount else 'free_relief')
            if row['area'] in ('green','tee') and not amount:
                row['phase']='free_place'
                return '果岭取不更靠洞、在果岭或一般区域的最近完全救济点放置；发球区内可重新选位置架球。完成后说“已完成免罚放置”。'
            row['phase']='drop'
            return '由本人从膝盖高度抛球。'+('从沙坑后延线在沙坑外救济，罚一杆。' if amount else '以最近完全救济点为基准，一杆范围内且不更靠洞，留在原规定球场区域。')
    if row['phase']=='free_place' and text=='已完成免罚放置':
        row['phase']='place_result'
        return finish_relief(state,flow,row,event,now,same_position=True)
    if row['phase']=='wrong_ball_location':
        if text=='仅在发球区换球开球':
            close_incident(flow,row)
            return '开球时选用的球随该次击球成为使用中球，已保留这杆，未按打错球追加处罚。'
        if text=='洞中打了别人的球':
            row['phase']='wrong_ball_target'
            return '打错球的是刚才记录的这一杆，还是一杆尚未记录的击球？'
    if row['phase']=='wrong_ball_target':
        if text not in ('刚才记录的这一杆打错球','错球击球尚未记录'):
            return '请确认错球击球是否已出现在实际用杆表里。'
        if text=='刚才记录的这一杆打错球':
            target=last_stroke(flow)
            if target:
                target['active']=False
                target['wrong_ball']=True
                from ball_rules import invalidate_score
                invalidate_score(state,flow['scope'][2])
        flow.pop('open_shot',None)
        row['phase']='wrong_ball_format'
        return '这场按比杆赛还是比洞赛处理？'
    if row['phase']=='wrong_ball_format' and text in ('比杆赛','比洞赛'):
        state['journey']['round']['play_format']=text
        if text=='比洞赛':
            state['journey']['round'].setdefault('hole_results',{})[str(flow['scope'][2])]='lost'
            close_incident(flow,row)
            return '比洞赛打错球按本洞负处理，已记录本洞结果。'
        add_penalty(flow,row,2,suffix='wrong_ball')
        row['phase']='wrong_ball_return'
        return '比杆赛记两杆处罚，错球击球不计入杆数。回原球或按规则处理原球，须在规定时限内纠正，完成后说“已回原球位置”。'
    if row['phase']=='wrong_ball_return' and text=='已回原球位置':
        return finish_restoring(state,flow,row,event,now)
    if row['phase']=='swing_intent' and text in ('有意击球但挥空','只是练习挥杆'):
        opening=flow.get('open_shot') or {}
        existing=next((item for item in flow['sequence'] if item['id']==opening.get('stroke_id')),None)
        if text=='只是练习挥杆':
            if existing:
                existing['active']=False
                from ball_rules import invalidate_score
                invalidate_score(state,flow['scope'][2])
            flow.pop('open_shot',None)
            close_incident(flow,row)
            return '已按练习挥杆处理，这次未增加击球或罚杆。'
        if not existing:
            origin=opening.get('origin') or position(state,now)
            add_stroke(flow,event['event_id']+'-whiff',flow['active_ball'],
                       opening.get('club'),origin,origin)
        else:
            existing.update(landing=existing.get('origin'),distance_m=0)
        flow.pop('open_shot',None)
        close_incident(flow,row)
        return '有意击球但挥空，已记一杆击球，球留在原位，未另加罚杆。'
    if row['phase']=='move_circumstance':
        if text=='不清楚':
            return '先核对球移动的原因和适用例外，确认后再记罚杆。'
        if text=='寻找辨认时意外碰动':
            return replace_prompt(flow,row,0)
        if text=='普通意外碰动':
            return replace_prompt(flow,row,0 if row['area'] in ('green','tee') else 1)
        if text=='故意移动':
            return replace_prompt(flow,row,0 if row['area']=='tee' else 1)
    if row['phase']=='move_natural':
        if text=='已在果岭放回或救济后跨区域':
            return replace_prompt(flow,row,0)
        if text=='都不是':
            close_incident(flow,row)
            return '按自然力量移动后的新位置打，未增加罚杆。请更新实际球位。'
        if text=='不清楚':
            return '先确认是否适用须放回的例外，再决定从原位置还是新位置打。'
    if row['phase']=='move_replace' and text=='已放回原位置':
        return finish_restoring(state,flow,row,event,now)
    return None
