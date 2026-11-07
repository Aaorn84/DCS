"""Explicit prospective club choice, separate from execution and general agreement."""
import re

def selection(text):
 if '?' in text or '？' in text:return None
 clean=re.sub(r'[\s，,。！!]','',text)
 m=re.fullmatch(r'(?:好(?:的)?|可以)?(?:那就|我想|我还是|还是|就|想)?(?:改用|换成|换用|使用|用|选)?(一号木|1号木|三号木|3号木|[2-7二两三四五六七](?:号铁|铁))(?:吧)?',clean)
 if not m:return None
 label=m[1]
 if label not in ('一号木','三号木'):label=label.translate(str.maketrans('二两三四五六七','2234567'))
 if label in ('一号木','1号木'):return {'key':'driver','label':'一号木'}
 if label in ('三号木','3号木'):return {'key':'three_wood','label':'3号木'}
 return {'key':'seven' if label.startswith('7') else 'long_iron','label':label}

def same_label(a,b):
 def norm(t):return t.replace('号','').replace('一','1').replace('三','3')
 return norm(a)==norm(b)
