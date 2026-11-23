"""Landing surface evidence, preserving user confirmation ahead of map inference."""
from round_state import canonical,fact_value
from report_geometry import mapped_polygons,polygon_contains
from surface_uncertainty import polygon_contains as uncertainty_contains

LABELS={'bunker':'沙坑','water':'水域','ob':'界外区域','green':'果岭','fairway':'球道','rough':'长草','fringe':'果岭环','unknown':'球位类型未确认'}

def classify(state,hole,shot,scope=None,polygons=None):
 j=state.get('journey',{});eid=fact_value({'facts':state.get('facts',{})},'context.course_snapshot')
 scope=scope or [(j.get('round') or {}).get('id'),eid,hole['number']]
 report=shot.get('landing_report')
 if not report:
  latest=j.get('reported_landing',{})
  if latest.get('stroke_id')==shot.get('id') and latest.get('scope')==canonical(scope):report=latest
 if report and report.get('stroke_id')==shot.get('id') and report.get('scope')==canonical(scope):
  from landing_types import normalize,label
  location=normalize(report);kind=location['lie_type']
  return dict(kind=kind,label=label(location),source='user_report',edge=False,area=location.get('area'),confirmation=location['confirmation'],green_status=location['green_status'])
 point=shot.get('landing')
 if not point:return None
 course=state.get('evidence',{}).get(eid,{}).get('data',{})
 polygons=polygons if polygons is not None else mapped_polygons(hole,course.get('reference_simulation') is True)
 for kind in ('ob','water','bunker','green','fairway'):
  rings=[r for r in polygons[kind].values() if polygon_contains(r,dict(point,accuracy_m=0))]
  if rings:
   edge=bool(point.get('accuracy_m',0)>0 and not any(uncertainty_contains(r,point) for r in rings))
   return dict(kind=kind,label=LABELS[kind],source='map_geometry',edge=edge,area=None,confirmation='pending',green_status='unknown')
 return None

def wording(evidence):
 if not evidence:return ''
 if evidence['source']=='user_report':
  if evidence.get('confirmation','confirmed')!='confirmed':return '你当时报告的位置是'+evidence['label']+'，尚待核实'
  return '你当时确认落在'+evidence['label']
 return '按地图判断落在'+evidence['label']+('边缘附近' if evidence.get('edge') else '内')
