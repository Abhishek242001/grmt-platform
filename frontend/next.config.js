/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Enforced as of Next 16 (403s + blocked HMR WebSocket otherwise) since the
  // browser reaches this dev server through Lightning's public proxy domain.
  allowedDevOrigins: ['*.cloudspaces.litng.ai'],
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        // Server-to-server call, never touches the browser — this is what
        // avoids CORS entirely rather than fighting it.
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
