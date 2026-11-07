"""Bounded preference and agreement parsing; never grant permission by substring."""
import re,unicodedata
YES={'当然','当然可以','可以','好的','好','好啊','好呀','好吧','没问题','没有问题','行','行啊','行的','可以的','可以啊','可以呀','没问题啊','ok','okay','yes','yesplease','sure','ofcourse','noproblem','noproblems'}
NO={'不','不要','不行','不可以','不用','不需要','不需要提醒','不用提醒','别提醒','不要提醒','no','nope','notok','不愿意','不想','拒绝'}
def agreement(text,positive=(),negative=()):
    text=unicodedata.normalize('NFKC',text).strip().lower()
    if re.search(r'[?？]|吗|也许|不确定|看情况|好像|考虑|可能|再看看',text):return None
    values=[]
    for part in re.split(r'[，,。.!！;；]+',text):
        token=re.sub(r'[\s\-]+','',part).strip()
        token=re.sub(r'^(?:嗯嗯|嗯|那就|那)','',token)
        if not token or token in ('谢谢','thanks','thankyou','please'):continue
        if token in YES or token in positive:values.append(True)
        elif token in NO or token in negative:values.append(False)
        else:return None
    return values[0] if values and all(v==values[0] for v in values) else None

def preferred_unit(text):
    text=unicodedata.normalize('NFKC',text);found=[]
    pattern=r'(?:更?(?:喜欢|习惯|偏好)(?:使用|用)?|改用|使用|用|改成|换成|改回|换回|改为|切换到|还是|而是|单位(?:为|是))\s*(码|米)'
    for m in re.finditer(pattern,text):
        before=text[max(0,m.start()-8):m.start()]
        if re.search(r'(?:不|别|不要|不想|不再|不太|不怎么)\s*$',before):continue
        found.append(m.group(1))
    return found[-1] if found else None

def agreement_without_unit(text,**kw):
    parts=re.split(r'[，,。.!！;；]+',text)
    return agreement('，'.join(p for p in parts if preferred_unit(p) is None),**kw)
