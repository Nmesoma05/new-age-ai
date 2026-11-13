import { Logo } from "@/components/Logo";

export const metadata = { title: "Offline" };

export default function Offline() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6 text-center">
      <Logo tagline />
      <h1 className="font-display text-[28px] font-bold">You&apos;re offline</h1>
      <p className="max-w-[40ch] text-[16px] text-muted">New Age AI needs a connection. Your work is saved on our servers, so nothing is lost. Reconnect and try again.</p>
      <a href="/start" className="inline-flex min-h-[44px] items-center rounded-m bg-orange px-5 font-semibold text-on-orange">Try again</a>
    </main>
  );
}
