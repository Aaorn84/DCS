export class ApiError extends Error {
  constructor(message: string, public status: number, public current?: any) {super(message);}
}
export async function request(base: string, path: string, token?: string, data?: unknown) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25000);
  try {
    const response = await fetch(base.replace(/\/$/, '') + path, {method: data === undefined ? 'GET' : 'POST',
      headers: {'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {})},
      body: data === undefined ? undefined : JSON.stringify(data), signal: controller.signal});
    const body = await response.json();
    if (!response.ok) throw new ApiError(body.error ?? '请求失败', response.status, body.current);
    return body;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new Error('暂时无法连接服务，本地记录仍然保留。请检查网络和服务地址。');
  } finally {clearTimeout(timer);}
}
