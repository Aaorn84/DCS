"""Resource controls shared by HTTP/core/DB boundaries; no database dependency."""
import os
class CapacityError(RuntimeError):pass
def integer(name,default,low,high):
 value=int(os.environ.get(name,str(default)))
 if not low<=value<=high:raise ValueError(name+' out of range')
 return value
