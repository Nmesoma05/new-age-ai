/** @type {import('next').NextConfig} */
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  // Only when served over https (staging/prod): browsers then refuse plain http for a year.
  ...(process.env.COOKIE_SECURE === "true"
    ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }] : []),
  // Staging must never be indexed by search engines.
  ...(process.env.NOINDEX === "true" ? [{ key: "X-Robots-Tag", value: "noindex, nofollow" }] : []),
];
const nextConfig = {
  reactStrictMode: true,
  output: "standalone", // the Docker image runs .next/standalone/server.js
  // Send page metadata in <head> up front for every visitor. With streamed metadata (Next 15 default for browsers)
  // the generic title could arrive after the app had set "Page · Workspace · Product" and overwrite it.
  htmlLimitedBots: /.*/,
  poweredByHeader: false,
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      // the service worker must update promptly; browsers check it on every visit
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache" }] },
    ];
  },
};
export default nextConfig;
