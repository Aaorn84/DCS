"""Explicit prospective club choice, separate from execution and general agreement."""
import re

def selection(text):
 if '?' in text or '？' in text:return None
 clean=re.sub(r'[\s，,。！!]','',text)
 m=re.fullmatch(r'(?:好(?:的)?|可以)?(?:那就|我想|我还是|还是|就|想)?(?:改用|换成|换用|使用|用|选)(一号木|1号木|三号木|3号木|[2-6](?:号铁|铁))',clean)
 if not m:return None
 label=m[1]
 if label in ('一号木','1号木'):return {'key':'driver','label':'一号木'}
 if label in ('三号木','3号木'):return {'key':'three_wood','label':'3号木'}
 return {'key':'long_iron','label':label}

def same_label(a,b):
 def norm(t):return t.replace('号','').replace('一','1').replace('三','3')
 return norm(a)==norm(b)
