import type { MetadataRoute } from "next";

// Installable app (home-screen icon, full-screen launch). No personal data is cached on the device.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "New Age AI",
    short_name: "New Age AI",
    description: "AI for creators, businesses and freelancers. A product of New Age Media.",
    id: "/",
    start_url: "/start",
    scope: "/",
    display: "standalone",
    background_color: "#171717",
    theme_color: "#171717",
    categories: ["business", "productivity"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
