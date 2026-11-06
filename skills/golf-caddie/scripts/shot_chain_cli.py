#!/usr/bin/env python3
"""Local JSON-lines / scenario runner for normalized shot attribution."""
import argparse
import json
import sys
from round_state import Engine, canonical


def handle(engine, req):
    action=req.get('action','event');rid=req.get('round_id','demo')
    if action=='create':engine.create(rid);return {'action':'commit','state':engine.state(rid)}
    if action=='shot':
        from shot_chain import shot_view
        return {'shot':shot_view(engine.state(rid),req['shot_id'])}
    if action in ('state','replay'):
        return {'state':engine.replay(rid) if action=='replay' else engine.state(rid)}
    if action=='event':
        event=req['event']
        return engine.command(rid, req.get('command_id',event['event_id']), 'attribution_event',event,
                              expected_version=req.get('expected_version'))
    raise ValueError('unsupported action')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',default=':memory:')
    p.add_argument('--owner',default='local-demo',help='Local principal only; not network authentication')
    p.add_argument('--scenario',help='JSON array of requests; omit for stdin JSON-lines')
    args=p.parse_args();engine=Engine(args.database,args.owner)
    try:
        if args.scenario:
            with open(args.scenario,encoding='utf-8') as f:requests=json.load(f)
            if not isinstance(requests,list):raise ValueError('scenario array required')
            source=(canonical(r) for r in requests)
        else:source=sys.stdin
        for line in source:
            if not line.strip():continue
            try:result=handle(engine,json.loads(line));print(canonical({'ok':True,'result':result}),flush=True)
            except (ValueError,KeyError,TypeError) as exc:
                print(canonical({'ok':False,'result':{'action':'reject','reason':str(exc)}}),flush=True)
    finally:engine.close()


if __name__=='__main__':main()
