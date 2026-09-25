interface GetHostParams {
  purpose?: string;
}

export const getHost = ({ purpose }: GetHostParams = {}): string => {
  if (typeof window !== 'undefined') {
    const { host, hostname, protocol } = window.location;
    // A URL query must never redirect authenticated traffic to another host.
    if (process.env.NEXT_PUBLIC_ASTERIA_API_URL) {
      return process.env.NEXT_PUBLIC_ASTERIA_API_URL;
    } else if (process.env.REACT_APP_ASTERIA_API_URL) {
      return process.env.REACT_APP_ASTERIA_API_URL;
    } else if (purpose === 'langgraph-gui') {
      return host.includes('localhost') ? 'http%3A%2F%2F127.0.0.1%3A8123' : `https://${host}`;
    } else {
      // Keep the exact browser hostname for host-scoped login cookies. The lab
      // Compose deployment publishes API and web on the same host, different
      // ports; a colleague's browser must not call its own 127.0.0.1.
      return `${protocol}//${hostname}:8018`;
    }
  }
  return '';
};
