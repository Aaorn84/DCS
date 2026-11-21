"""Small landing taxonomy; surface and area are independent, hazards stay separate."""
import re
TYPES={'球道':'fairway','长草':'rough','沙坑':'bunker','果岭环':'fringe','果岭':'green'}
LABELS={v:k for k,v in TYPES.items()};LABELS['unknown']='球位类型未确认'
AREAS={'greenside':'果岭边','fairway_left':'球道左侧','fairway_right':'球道右侧','fairway_center':'球道中间'}

def fields(text,lie_type='unknown',side=None,uncertain=False,boundary_uncertain=False):
 greenside=bool(re.search(r'果岭边|果岭附近|果岭外|果岭[左右前后](?:边|侧|方)|果岭环|果岭裙|环上|前沿',text))
 area='greenside' if greenside else None
 if not area and '球道' in text:
  area='fairway_left' if side=='左侧' else 'fairway_right' if side=='右侧' else 'fairway_center' if side=='中间' else None
 confirmation='confirmed' if lie_type!='unknown' and (not uncertain or boundary_uncertain) else 'pending'
 green_status='on' if lie_type=='green' and confirmation=='confirmed' else 'off' if lie_type!='unknown' and confirmation=='confirmed' else 'off' if re.search(r'果岭外|没上去|过了果岭',text) and not uncertain else 'unknown'
 return dict(lie_type=lie_type,area=area,source='user_report',confirmation=confirmation,green_status=green_status)

def normalize(report):
 kind=report.get('lie_type')
 if kind not in LABELS:
  kind=TYPES.get(report.get('lie'),'unknown')
  if re.search(r'果岭环|果岭裙|停在环上',report.get('text','')):kind='fringe'
 area=report.get('area')
 if not area and report.get('lie') in ('果岭附近','果岭边','果岭环'):area='greenside'
 confirmation=report.get('confirmation') or ('confirmed' if kind!='unknown' else 'pending')
 return dict(lie_type=kind,area=area,side=report.get('side'),source=report.get('source','user_report'),confirmation=confirmation,green_status=report.get('green_status','on' if kind=='green' and confirmation=='confirmed' else 'off' if kind!='unknown' and confirmation=='confirmed' else 'unknown'))

def label(location):
 kind=location['lie_type'];area=location.get('area');side=location.get('side')
 if kind=='unknown':return AREAS.get(area,'落点附近')+'（球位类型待确认）'
 if kind=='fringe':return ('左侧' if side=='左侧' else '右侧' if side=='右侧' else '')+'果岭环'
 if kind=='green':return '果岭'+(side if side in ('左侧','右侧') else '上')
 if kind=='fairway' and area in ('fairway_left','fairway_right','fairway_center'):return AREAS[area]
 if area=='greenside':return ('果岭左侧' if side=='左侧' else '果岭右侧' if side=='右侧' else '果岭边')+'的'+LABELS[kind]
 if area:return AREAS.get(area,area)+'的'+LABELS[kind]
 return (side or '')+LABELS[kind]

def compact(report):
 return {k:report[k] for k in ('stroke_id','scope','lie','lie_type','area','side','source','confirmation','green_status','event_id') if k in report}
