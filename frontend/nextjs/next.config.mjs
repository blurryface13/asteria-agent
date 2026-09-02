/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // jsdom (pulled in by isomorphic-dompurify) breaks when webpack tries to
    // bundle its dynamic requires for SSR; keep it as a native Node require instead.
    serverComponentsExternalPackages: ['jsdom', 'isomorphic-dompurify'],
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
