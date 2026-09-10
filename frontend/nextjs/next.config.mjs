/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // Keep build concurrency bounded on development machines with a low
    // per-process file/worker limit. This avoids a long first build with
    // many workers competing for the same descriptor budget.
    cpus: 1,
    // jsdom (pulled in by isomorphic-dompurify) breaks when webpack tries to
    // bundle its dynamic requires for SSR; keep it as a native Node require instead.
    serverComponentsExternalPackages: ['jsdom', 'isomorphic-dompurify'],
  },
  webpack(config, { dev }) {
    if (dev) {
      // macOS may expose only a small FSEvents/file-descriptor budget to
      // processes launched from the desktop. Polling is slower per change,
      // but makes the dev server deterministic instead of failing with
      // EMFILE during startup.
      config.watchOptions = {
        ...config.watchOptions,
        poll: 1000,
        aggregateTimeout: 300,
      };
    }
    return config;
  },
  images: {
    remotePatterns: [
      {
        hostname: 'www.google.com',
      },
      {
        hostname: 'www.google-analytics.com',
      },
      {
        hostname: 'localhost',
      }
    ],
  },
  // Proxy /outputs requests to the backend server for generated images
  async rewrites() {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
    return [
      {
        source: '/outputs/:path*',
        destination: `${backendUrl}/outputs/:path*`,
      },
    ];
  },
};

// Keep the local development server independent from the optional PWA plugin.
// The research UI and evaluation workflow do not require a service worker.
export default nextConfig;
