/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        // Server-to-server call, same machine, same process boundary —
        // never touches the browser, so CORS/Lightning's proxy gate
        // never enters into it.
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
