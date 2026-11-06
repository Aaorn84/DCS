#!/usr/bin/env python3
"""Local JSON-lines adapter. Not an authenticated network service."""
import argparse
import json
import sys
from round_state import Engine, StateError, attribute, canonical


def handle(engine, request):
    action, round_id = request.get('action', 'command'), request['round_id']
    if action == 'create':
        engine.create(round_id)
        return engine.state(round_id)
    if action == 'state':
        return engine.state(round_id)
    if action == 'replay':
        return engine.replay(round_id)
    if action == 'attribute':
        return attribute(request['text'], engine.state(round_id), request.get('question_id'), request.get('shot_id'))
    if action == 'command':
        return engine.command(round_id, request['command_id'], request['kind'], request['payload'],
                              expected_version=request.get('expected_version'))
    raise StateError('unsupported action')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--owner', required=True, help='Local test principal; production uses authenticated server principal')
    args = parser.parse_args()
    engine = Engine(args.database, args.owner)
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                result = handle(engine, json.loads(line))
                print(canonical({'ok': True, 'result': result}), flush=True)
            except (ValueError, KeyError, TypeError) as exc:
                print(canonical({'ok': False, 'error': str(exc)}), flush=True)
    finally:
        engine.close()


if __name__ == '__main__':
    main()
