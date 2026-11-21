"""A shorter landing request adjusts the discussion without committing a stroke."""
import re

def respond(state,text):
 c=state.get('journey',{}).get('consultation') or {}
 clean=re.sub(r'[\s，,。！!？?]','',text)
 if c.get('phase')!='plan' or not re.fullmatch(r'(?:我)?(?:想|想要|打算|希望)?(?:打|落)(?:得)?短(?:一?点|一些)(?:吧)?',clean):return None
 c['shorter_landing_requested']=True
 return '好，改看更短的落点。短于攻果岭所需Carry可能停在果岭前；先核对那里的障碍和滚动空间。你想换哪支杆？'

def selection_wording(state,chosen):
 c=state.get('journey',{}).get('consultation') or {}
 if not c.get('shorter_landing_requested'):return chosen
 text='按较短落点的思路打'
 m=re.fullmatch(r'(\d+)度杆',chosen['club'])
 ranges=state['journey'].get('profile',{}).get('lofted_wedge_ranges',{}).get('value',{})
 value=ranges.get(m[1]) if m else None
 if value:
  low,high=value['low'],value['high'];carry=str(low) if low==high else f'{low}–{high}'
  text+=f'，已知Carry约{carry}{value["units"]}，落点可能在果岭前，现场确认障碍和滚动空间'
 return dict(chosen,target='shorter_landing',wording=text)
