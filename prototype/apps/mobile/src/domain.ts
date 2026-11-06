export type Kind = 'profile' | 'club' | 'memory' | 'round';
export type Score = {total: number; penalty: number | null; putts: number | null};
export type Profile = {name: string; style: string; quiet: boolean};
export type Club = {name: string; distance: number; distanceType: 'carry' | 'total'; source: 'user_confirmed'};
export type Memory = {text: string; source: 'user_confirmed'};
export type Round = {course: string; scores: (Score | null)[]; status: 'active' | 'finished'};
export type Data = Profile | Club | Memory | Round;
export type Row = {id: string; kind: Kind; version: number; deleted: boolean; data: Data};
export type Operation = {operationId: string; id: string; kind: Kind; baseVersion: number; deleted: boolean; data: Data};
export type Chat = {role: 'user' | 'assistant'; text: string; label?: string};
export type State = {records: Row[]; pending: Operation[]; chat: Chat[]; voice?: import('./voiceFlow').VoiceFlow};
export const empty = (): State => ({records: [], pending: [], chat: []});
export const same = (a: {kind: Kind; id: string}, b: {kind: Kind; id: string}) => a.kind === b.kind && a.id === b.id;
export function edit(state: State, kind: Kind, id: string, data: Data, operationId: string, deleted = false): State {
  if (!deleted) {
    const values = data as any;
    if (kind === 'profile' && (!values.name?.trim() || values.name.length > 30 || !values.style?.trim() || values.style.length > 30))
      throw new Error('称呼和交流风格各需1—30个字符');
    if (kind === 'club' && (!values.name?.trim() || values.name.length > 30 || !Number.isInteger(values.distance) || values.distance < 1 || values.distance > 400))
      throw new Error('请填写1—30字球杆名称和1—400米整数距离');
    if (kind === 'memory' && (!values.text?.trim() || values.text.length > 500))
      throw new Error('记忆内容需1—500字');
  }
  const old = state.records.find(r => same(r, {kind, id}));
  if (old?.deleted && !deleted) throw new Error('已删除记录不能恢复，请新建');
  const row = {id, kind, data: deleted ? {} as Data : data, version: (old?.version ?? 0) + 1, deleted};
  return {...state, records: [...state.records.filter(r => !same(r, row)), row],
    // Clear transient chat to avoid deleted memories remaining in a local transcript.
    chat: deleted && kind === 'memory' ? [] : state.chat,
    pending: [...state.pending, {operationId, id, kind, data: row.data, baseVersion: old?.version ?? 0, deleted}]};
}
export function acknowledge(state: State, operation: Operation, server: Row): State {
  const pending = state.pending.filter(o => o.operationId !== operation.operationId);
  const newer = pending.some(o => same(o, operation));
  return {...state, pending, records: newer ? state.records : [...state.records.filter(r => !same(r, server)), server]};
}
export function merge(state: State, remote: Row[]): State {
  const merged = new Map(state.records.map(r => [`${r.kind}:${r.id}`, r]));
  for (const row of remote) {
    if (!state.pending.some(o => same(o, row))) merged.set(`${row.kind}:${row.id}`, row);
  }
  return {...state, records: [...merged.values()]};
}
export function resolveConflict(state: State, key: {kind: Kind; id: string}, server: Row | null, keepLocal: boolean, operationId: string): State {
  const local = state.records.find(r => same(r, key));
  const base = {...state, pending: state.pending.filter(o => !same(o, key)),
    records: state.records.filter(r => !same(r, key)), chat: []};
  if (server) base.records.push(server);
  if (!keepLocal || !local || server?.deleted) return base;
  return edit(base, key.kind, key.id, local.data, operationId, local.deleted);
}
export function score(total: number, penalty: number | null, putts: number | null): Score {
  if (!Number.isInteger(total) || ![penalty,putts].every(n=>n===null||(Number.isInteger(n)&&n>=0)) || total < 1 || total > 30 || (penalty??0)+(putts??0) > total)
    throw new Error('请输入有效整数；总杆包含罚杆，且不能少于罚杆与推杆之和');
  return {total, penalty, putts};
}
export function recap(round: Round) {
  const scores = round.scores.filter((s): s is Score => s !== null);
  return {holes: scores.length, total: scores.reduce((n, s) => n + s.total, 0),
    penalty: scores.reduce((n, s) => n + (s.penalty ?? 0), 0), putts: scores.reduce((n, s) => n + (s.putts ?? 0), 0)};
}
