import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { ToastProvider } from "@/components/ui";
import { SwRegister } from "@/components/SwRegister";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "New Age AI", template: "%s · New Age AI" },
  description: "New Age AI, a product of New Age Media: AI tools for creators and agencies, business owners, and freelancers.",
  applicationName: "New Age AI",
  manifest: "/manifest.webmanifest",
  icons: { icon: [{ url: "/favicon.png", sizes: "48x48", type: "image/png" }],
           apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }] },
  appleWebApp: { capable: true, title: "New Age AI", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = { themeColor: "#171717", width: "device-width", initialScale: 1 };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  await headers();  // render per request so every page carries this request's CSP nonce
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500;600&display=swap" />
      </head>
      <body className="min-h-screen antialiased"><ToastProvider>{children}</ToastProvider><SwRegister /></body>
    </html>
  );
}
