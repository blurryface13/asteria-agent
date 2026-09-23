interface GetHostParams {
  purpose?: string;
}

export const getHost = ({ purpose }: GetHostParams = {}): string => {
  if (typeof window !== 'undefined') {
    let { host } = window.location;
    // A URL query must never redirect authenticated traffic to another host.
    if (process.env.NEXT_PUBLIC_ASTERIA_API_URL) {
      return process.env.NEXT_PUBLIC_ASTERIA_API_URL;
    } else if (process.env.REACT_APP_ASTERIA_API_URL) {
      return process.env.REACT_APP_ASTERIA_API_URL;
    } else if (purpose === 'langgraph-gui') {
      return host.includes('localhost') ? 'http%3A%2F%2F127.0.0.1%3A8123' : `https://${host}`;
    } else {
      // Both loopback hostnames are used by the local startup script.  Treat
      // them identically; otherwise 127.0.0.1 was incorrectly upgraded to
      // https://127.0.0.1:3000 and browser requests failed before reaching
      // the backend.
      const isLocalhost = host.includes('localhost') || host.startsWith('127.0.0.1');
      return isLocalhost ? 'http://127.0.0.1:8018' : `https://${host}`;
    }
  }
  return '';
};
