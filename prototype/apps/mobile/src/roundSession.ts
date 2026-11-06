import {request} from './api';
export type SessionEvent = {
  event_id: string; revision?: number; phase?: 'partial' | 'final'; observed_at: string;
} & ({type: 'voice'; text: string} | {type: 'gps'; data: {latitude: number; longitude: number; accuracy_m: number}} |
     {type: 'course'; data: {course_id: string; map_version: string; crs: 'WGS84'; holes: unknown[]}});
export type SessionSnapshot = {version: number; facts: Record<string, unknown>; session?: unknown};
export type SessionReply = {result: {text: string; saved: boolean; speak_allowed: boolean; version: number; pause?: boolean}; state: SessionSnapshot};
/** Authenticated typed bridge. Retry a lost receipt with the exact SAME IDs and payload.
 * Do not also save the score through the legacy voiceFlow /sync path.
 */
export class RoundSession {
  constructor(private base: string, private token: string, private roundId: string) {}
  async create(): Promise<{state: SessionSnapshot}> {
    return request(this.base, '/round-state', this.token, {action:'create', round_id:this.roundId});
  }
  async snapshot(): Promise<{state: SessionSnapshot}> {
    return request(this.base, '/round-state', this.token, {action:'snapshot', round_id:this.roundId});
  }
  async submit(operationId: string, event: SessionEvent, expectedVersion?: number): Promise<SessionReply> {
    return request(this.base, '/round-state', this.token,
      {action:'event', round_id:this.roundId, operation_id:operationId, event, expected_version:expectedVersion});
  }
}
