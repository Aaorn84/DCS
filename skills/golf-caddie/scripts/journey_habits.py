"""Learn from explicit skips of a live optional previous-club prompt."""
import hashlib
import re

from journey_recovery import live_club_prompt
from journey_tee_options import silent
from round_state import canonical, require

DISABLE = '以后不用问上一杆用杆'
ENABLE = '恢复询问上一杆用杆'
SKIPS = {'跳过', '不记', '先不记'}
THRESHOLD = 3


def reduce_journey(state, event, seq, now):
    require(event.get('protocol_version') == 53, 'unsupported habit protocol')
    event_id = event.get('event_id')
    require(isinstance(event_id, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}', event_id)), 'invalid event id')
    digest = hashlib.sha256(canonical(event).encode()).hexdigest()
    journey = state.get('journey', {})
    prior = journey.get('habit_receipts', {}).get(event_id)
    if prior:
        require(prior == digest, 'event id reused with different payload')
        return {'text': '', 'speak_allowed': False, 'duplicate': True}

    message = event.get('type') == 'message'
    text = event.get('text', '').strip().rstrip('。！!')
    active = journey.get('stage') == 'active'
    allowed = journey.get('memory_allowed') is True
    live_prompt = message and allowed and not silent(state) and live_club_prompt(state, now)
    skipped = live_prompt and text in SKIPS
    prompt_key = journey['pending_previous_club']['key'] if live_prompt else None

    if message and active and text in (DISABLE, ENABLE) and not silent(state):
        enabled = text == ENABLE
        journey['profile']['shot_recording'] = {'value': enabled, 'source': 'user_report', 'event_id': event_id}
        journey.pop('pending_previous_club', None)
        journey.pop('previous_club_skip_count', None)
        reply = '好，需要时我会再问上一杆用的什么杆。' if enabled else '好，我以后等你主动告诉我用杆。'
        result = {'text': reply, 'speak_allowed': True}
    else:
        from journey import reduce_journey as previous

        adapted = dict(event, protocol_version=52)
        if skipped:
            adapted['text'] = text
        result = previous(state, adapted, seq, now)
        journey = state['journey']
        if journey.get('memory_allowed') is not True:
            journey.pop('previous_club_skip_count', None)
        elif live_prompt and journey.get('previous_club_reports', {}).get(prompt_key, {}).get('event_id') == event_id:
            if journey.get('previous_club_skip_count', 0) < THRESHOLD:
                journey.pop('previous_club_skip_count', None)
        elif skipped and result.get('text') == '好，这杆的用杆先留空。':
            count = journey.get('previous_club_skip_count', 0) + 1
            journey['previous_club_skip_count'] = min(count, THRESHOLD + 1)
            if count == THRESHOLD:
                result = {**result, 'text': '这杆先留空。最近几次你都跳过了用杆补问。想让我以后少问，可以说“以后不用问上一杆用杆”。'}

    journey.setdefault('habit_receipts', {})[event_id] = digest
    return result
