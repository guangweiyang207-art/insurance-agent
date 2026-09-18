import { useEffect, useState } from 'react';

import { AdvisorPage } from './AdvisorPage';
import { ApplicationPage } from './ApplicationPage';
import { logoutSession, refreshSession } from './api';
import { clearSession, readSession, saveSession, shouldRefreshSession, tokenExpiresAt } from './auth';
import { HomePage } from './HomePage';
import type { AuthSession } from './types';

function navigate(path: string) {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function applyPath(target: { productId: string; planId: string; itemId: string }) {
  const params = new URLSearchParams({
    product_id: target.productId,
    plan_id: target.planId,
    item_id: target.itemId,
  });
  return `/apply?${params.toString()}`;
}

export default function App() {
  const [path, setPath] = useState(window.location.pathname);
  const [session, setSession] = useState<AuthSession | null>(() => readSession());

  useEffect(() => {
    const updatePath = () => setPath(window.location.pathname);
    window.addEventListener('popstate', updatePath);
    return () => window.removeEventListener('popstate', updatePath);
  }, []);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    let timer: number | undefined;

    async function renew() {
      if (!session) return;
      try {
        if (shouldRefreshSession(session)) {
          const nextSession = await refreshSession();
          if (cancelled) return;
          saveSession(nextSession);
          setSession(nextSession);
          return;
        }
        schedule(session);
      } catch {
        if (!cancelled) sessionExpired();
      }
    }

    function schedule(currentSession: AuthSession) {
      const expiresAt = tokenExpiresAt(currentSession.access_token);
      const refreshAt = expiresAt ? expiresAt - Date.now() - 5 * 60 * 1000 : 60 * 1000;
      timer = window.setTimeout(() => void renew(), Math.max(10 * 1000, refreshAt));
    }

    if (shouldRefreshSession(session)) {
      void renew();
    } else {
      schedule(session);
    }
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [session]);

  function authenticated(nextSession: AuthSession) {
    saveSession(nextSession);
    setSession(nextSession);
  }

  function logout() {
    void logoutSession().catch(() => undefined);
    clearSession();
    setSession(null);
    if (path === '/advisor' || path === '/apply') navigate('/');
  }

  function sessionExpired() {
    clearSession();
    setSession(null);
    navigate('/');
  }

  if (path === '/advisor' && session) {
    return (
      <AdvisorPage
        session={session}
        onBack={() => navigate('/')}
        onSessionExpired={sessionExpired}
        onApplyProduct={(target) => navigate(applyPath(target))}
      />
    );
  }

  if (path === '/apply' && session) {
    return (
      <ApplicationPage
        session={session}
        onBack={() => navigate('/advisor')}
        onSessionExpired={sessionExpired}
      />
    );
  }

  return (
    <HomePage
      session={session}
      initialAuthMode={path === '/advisor' || path === '/apply' ? 'login' : null}
      onAuthenticated={authenticated}
      onLogout={logout}
      onConsult={() => navigate('/advisor')}
    />
  );
}
