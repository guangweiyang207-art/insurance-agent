import type {
  AuthSession,
  ChatHistory,
  ChatThread,
  InsuranceCategory,
  PlanInterrupt,
  ProductPage,
} from './types';

const BUSINESS_API = '/business-api/api/v1';
const AGENT_API = '/agent-api/api/v1';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BUSINESS_API}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new ApiError(error?.message ?? '请求失败，请稍后重试', response.status);
  }
  return response.json() as Promise<T>;
}

async function authorizedBusinessRequest<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${BUSINESS_API}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new ApiError(error?.message ?? '请求失败，请稍后重试', response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function agentRequest<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${AGENT_API}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new ApiError(error?.detail ?? error?.message ?? '请求失败，请稍后重试', response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function listProducts(
  category: InsuranceCategory | 'all',
  signal?: AbortSignal,
): Promise<ProductPage> {
  const params = new URLSearchParams({ page: '1', page_size: '20' });
  if (category !== 'all') {
    params.set('category', category);
  }
  return request<ProductPage>(`/products?${params}`, { signal });
}

export function login(username: string, password: string): Promise<AuthSession> {
  return request<AuthSession>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function register(
  username: string,
  email: string,
  password: string,
): Promise<AuthSession> {
  return request<AuthSession>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  });
}

export function refreshSession(): Promise<AuthSession> {
  return request<AuthSession>('/auth/refresh', {
    method: 'POST',
  });
}

export async function logoutSession(): Promise<void> {
  await request<{ ok: boolean }>('/auth/logout', {
    method: 'POST',
  });
}

export function markPlanItemInsured(
  token: string,
  planId: string,
  itemId: string,
): Promise<unknown> {
  return authorizedBusinessRequest<unknown>(
    `/insurance-plans/${encodeURIComponent(planId)}/items/${encodeURIComponent(itemId)}/insured`,
    token,
    { method: 'PATCH' },
  );
}

export function getInsurancePlan(token: string, planId: string): Promise<unknown> {
  return authorizedBusinessRequest<unknown>(
    `/insurance-plans/${encodeURIComponent(planId)}`,
    token,
  );
}

export function listChatThreads(token: string): Promise<ChatThread[]> {
  return agentRequest<ChatThread[]>('/chat-threads', token);
}

export function createChatThread(token: string, title = '保险咨询'): Promise<ChatThread> {
  return agentRequest<ChatThread>('/chat-threads', token, {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export function getChatHistory(
  token: string,
  threadId: string,
  signal?: AbortSignal,
): Promise<ChatHistory> {
  return agentRequest<ChatHistory>(`/chat-threads/${threadId}/messages`, token, { signal });
}

export function renameChatThread(
  token: string,
  threadId: string,
  title: string,
): Promise<ChatThread> {
  return agentRequest<ChatThread>(`/chat-threads/${threadId}`, token, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });
}

export async function deleteChatThread(token: string, threadId: string): Promise<void> {
  await agentRequest<void>(`/chat-threads/${threadId}`, token, {
    method: 'DELETE',
  });
}

interface ChatStreamHandlers {
  onMessage: (chunk: string) => void;
  onAdditionalInfo?: (info: unknown) => void;
  onInterrupt?: (interrupt: PlanInterrupt) => void;
}

export async function streamChat(
  token: string,
  threadId: string,
  input: { message?: string; decision?: Record<string, unknown> },
  handlers: ChatStreamHandlers,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<void> {
  const controller = new AbortController();
  let timedOut = false;
  let timer: ReturnType<typeof setTimeout>;
  const resetTimeout = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, options.timeoutMs ?? 70_000);
  };
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  if (options.signal?.aborted) abort();
  resetTimeout();
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    const response = await fetch(`${AGENT_API}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ thread_id: threadId, ...input }),
      signal: controller.signal,
    });
    if (!response.ok || !response.body) {
      const error = await response.json().catch(() => null);
      throw new ApiError(error?.detail ?? error?.message ?? '消息发送失败，请稍后重试', response.status);
    }

    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let lines: string[] = [];
    let completed = false;
    let interrupted = false;
    let receivedContent = false;
    const dispatch = () => {
      const result = handleSseEvent(lines.join('\n'), handlers);
      lines = [];
      if (result === 'ignored') return;
      resetTimeout();
      if (result === 'done') completed = true;
      else {
        receivedContent = true;
        if (result === 'interrupt') interrupted = true;
      }
    };
    const consumeLines = (flush = false) => {
      while (!completed) {
        const lineEnd = buffer.search(/[\r\n]/);
        if (lineEnd === -1) break;
        // A CRLF pair can be split across two network chunks.
        if (!flush && buffer[lineEnd] === '\r' && lineEnd === buffer.length - 1) break;
        const line = buffer.slice(0, lineEnd);
        const separatorLength = buffer.slice(lineEnd, lineEnd + 2) === '\r\n' ? 2 : 1;
        buffer = buffer.slice(lineEnd + separatorLength);
        if (line === '') dispatch();
        else lines.push(line);
      }
    };

    while (!completed) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      consumeLines(done);
      if (done) {
        if (!completed && (buffer || lines.length)) {
          if (buffer) lines.push(buffer);
          dispatch();
        }
        break;
      }
    }
    if (!completed && !interrupted) {
      throw new Error('回复连接已中断，已收到的内容仍保留。请重新打开本会话查看保存结果后再重试。');
    }
    if (!receivedContent) {
      throw new Error('服务未返回回复内容，请稍后重试。');
    }
  } catch (reason) {
    if (timedOut) throw new Error('等待回复超时，请稍后重新打开本会话查看保存结果后再重试。');
    throw reason;
  } finally {
    clearTimeout(timer!);
    options.signal?.removeEventListener('abort', abort);
    await reader?.cancel().catch(() => undefined);
    reader?.releaseLock();
  }
}

function handleSseEvent(
  eventText: string,
  handlers: ChatStreamHandlers,
): 'message' | 'additional_info' | 'interrupt' | 'done' | 'ignored' {
  const lines = eventText.split('\n');
  const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() || 'message';
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).replace(/^ /, ''))
    .join('\n');
  if (event === 'error') {
    const parsed = parseJsonLike(data);
    const detail = parsed && typeof parsed === 'object'
      ? (parsed as { message?: unknown; detail?: unknown }).message
        ?? (parsed as { detail?: unknown }).detail
      : parsed;
    throw new Error(typeof detail === 'string' && detail ? detail : '回复生成失败，请稍后重试。');
  }
  if (event === 'done') return 'done';
  if (!data) return 'ignored';
  if (event === 'message') {
    const content = parseSseMessage(data);
    if (!content) return 'ignored';
    handlers.onMessage(content);
    return 'message';
  }
  if (event === 'interrupt') {
    const interrupt = parseInterrupt(data);
    if (!interrupt) throw new Error('方案确认信息不完整，请重新打开本会话后重试。');
    handlers.onInterrupt?.(interrupt);
    return 'interrupt';
  }
  if (event === 'additional_info') {
    handlers.onAdditionalInfo?.(parseJsonLike(data) ?? data);
    return 'additional_info';
  }
  return 'ignored';
}

function parseSseMessage(data: string): string {
  try {
    const value = JSON.parse(data) as unknown;
    return typeof value === 'string' ? value : JSON.stringify(value);
  } catch {
    return data;
  }
}

function parseInterrupt(data: string): PlanInterrupt | null {
  const parsed = parseJsonLike(data);
  const value = Array.isArray(parsed) ? parsed[0] : parsed;
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Partial<PlanInterrupt>;
  if (!('plan' in candidate) || typeof candidate.confirm_info !== 'string') return null;
  return {
    plan: candidate.plan,
    confirm_info: candidate.confirm_info,
    action: Array.isArray(candidate.action)
      ? candidate.action.filter((item): item is 'approve' | 'reject' =>
          item === 'approve' || item === 'reject',
        )
      : ['approve', 'reject'],
  };
}

function parseJsonLike(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
}
