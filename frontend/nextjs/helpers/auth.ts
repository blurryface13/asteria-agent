const TOKEN_KEY = 'bunny_auth_token';
const EMAIL_KEY = 'bunny_auth_email';

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
// A 401 response means the token is missing/expired/invalid (e.g. it expired
// naturally, or JWT_SECRET rotated server-side), so clear the stale local
// session and send the user back to /login instead of failing silently.
export async function authFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const response = await fetch(input, { ...init, headers });
  if (response.status === 401 && typeof window !== 'undefined' && window.location.pathname !== '/login') {
    clearAuth();
    window.location.href = '/login';
  }
  return response;
}
