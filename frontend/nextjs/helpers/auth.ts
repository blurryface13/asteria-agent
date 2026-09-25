const TOKEN_KEY = 'bunny_auth_token';
const EMAIL_KEY = 'bunny_auth_email';
const DISPLAY_NAME_KEY = 'asteria.displayName';
const DISPLAY_NAME_EMAIL_KEY = 'asteria.displayNameEmail';

// This flag is intentionally public because it only controls the browser-side
// development experience. The backend has its own matching flag; production
// deployments must leave both flags disabled.
export function isLocalAuthBypassEnabled(): boolean {
  return process.env.NEXT_PUBLIC_ASTERIA_DEV_AUTH_BYPASS === '1';
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage?.getItem(TOKEN_KEY) || null;
  } catch {
    return null;
  }
}

export function setAuth(token: string, email: string) {
  try {
    if(getAuthEmail()!==email){
      // Only transient UI selections; preserve legacy reports/drafts untouched.
      for(const key of ['asteria.activeProjectId','asteria.knowledgeSelection','chatBoxSettings','apiVariables','domainFilters'])window.localStorage?.removeItem(key);
    }
    window.localStorage?.setItem(TOKEN_KEY, token);
    window.localStorage?.setItem(EMAIL_KEY, email);
  } catch {
    // Ignore storage failures; AuthGuard will send the user back to login.
  }
}

export function getAuthEmail(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage?.getItem(EMAIL_KEY) || null;
  } catch {
    return null;
  }
}

export function getDisplayName(): string {
  const email = getAuthEmail();
  if (typeof window === 'undefined') return email?.split('@')[0] || '用户';
  try {
    if (email && window.localStorage.getItem(DISPLAY_NAME_EMAIL_KEY) === email) {
      return window.localStorage.getItem(DISPLAY_NAME_KEY) || email.split('@')[0];
    }
  } catch {
    // The account identifier remains a safe fallback without browser storage.
  }
  return email?.split('@')[0] || '用户';
}

export function setDisplayName(name: string): void {
  const email = getAuthEmail();
  if (!email || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(DISPLAY_NAME_KEY, name);
    window.localStorage.setItem(DISPLAY_NAME_EMAIL_KEY, email);
  } catch {
    // Display names are optional browser-only preferences.
  }
}

export function clearAuth() {
  try {
    window.localStorage?.removeItem(TOKEN_KEY);
    window.localStorage?.removeItem(EMAIL_KEY);
  } catch {
    // Nothing else to clear when localStorage is unavailable.
  }
}

export function authHeader(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Drop-in replacement for fetch() that adds the Authorization header for
// every call - used for all client-side requests to our own /api/* proxy
// routes (which then forward the header on to the Python backend).
// A 401 normally means the token is missing/expired/invalid (e.g. it expired
// naturally, or JWT_SECRET rotated server-side), so clear the stale local
// session and send the user back to /login. In explicit local bypass mode,
// do not turn a frontend/backend configuration mismatch into a login loop;
// return the real 401 so the calling feature can display its actual error.
export async function authFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const response = await fetch(input, { credentials: 'include', ...init, headers });
  if (response.status === 401 && typeof window !== 'undefined' && window.location.pathname !== '/login') {
    if (isLocalAuthBypassEnabled()) {
      const target = typeof input === 'string' ? input : input.toString();
      console.error(
        `[auth] Local bypass is enabled, but the backend rejected ${target}. ` +
        'Check that the backend was started with ASTERIA_DEV_AUTH_BYPASS=1 and that the API URL is correct.'
      );
    } else {
      clearAuth();
      window.location.href = '/login';
    }
  }
  return response;
}
