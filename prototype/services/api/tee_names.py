"""Tee labels at the presentation boundary; normalize current spoken labels."""
import re

def display(value):
    if isinstance(value,str):
        return re.sub(r'([蓝白红黑黄金绿银])台',r'\1Tee',value)
    if isinstance(value,list):return [display(item) for item in value]
    if isinstance(value,dict):return {key:display(item) for key,item in value.items()}
    return value

def normalize_input(value):
    return re.sub(r'([蓝白红黑黄金绿银])\s*tee',r'\1台',value,flags=re.I)
