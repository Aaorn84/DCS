"""Optional stateless section validation; clients without it still receive full views."""
import hashlib,json
SECTIONS=('simulation.paths','simulation.test_stakes','simulation.positions','round_records','score_summary','profile','carry_estimates','history','round_review')

def compact(view,known):
    out=dict(view);revisions={};unchanged=[]
    for path in SECTIONS:
        parts=path.split('.');parent=out
        if len(parts)==2:
            if not isinstance(out.get(parts[0]),dict):continue
            # Never mutate the domain view or another section sharing this parent.
            out[parts[0]]=dict(out[parts[0]]);parent=out[parts[0]]
        key=parts[-1]
        if key not in parent:continue
        raw=json.dumps(parent[key],ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
        digest=hashlib.sha256(raw.encode()).hexdigest();revisions[path]=digest
        if known.get(path)==digest:
            del parent[key];unchanged.append(path)
    return dict(journey=out,journey_revisions=revisions,journey_unchanged=unchanged)
