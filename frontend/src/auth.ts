import type { AuthSession } from './types';

const STORAGE_KEY = 'insurance-mall-auth-v1';

export function readSession(): AuthSession | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value ? (JSON.parse(value) as AuthSession) : null;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function saveSession(session: AuthSession): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

export function tokenExpiresAt(accessToken: string): number | null {
  const payload = decodeJwtPayload(accessToken);
  return typeof payload?.exp === 'number' ? payload.exp * 1000 : null;
}

export function shouldRefreshSession(session: AuthSession, refreshWindowMs = 5 * 60 * 1000): boolean {
  const expiresAt = tokenExpiresAt(session.access_token);
  if (!expiresAt) return false;
  return expiresAt - Date.now() <= refreshWindowMs;
}

function decodeJwtPayload(accessToken: string): Record<string, unknown> | null {
  const payload = accessToken.split('.')[1];
  if (!payload) return null;
  try {
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    return JSON.parse(window.atob(padded)) as Record<string, unknown>;
  } catch {
    return null;
  }
}
