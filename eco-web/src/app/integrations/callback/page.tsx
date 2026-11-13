"use client";
// The provider sends the browser here after consent. We hand {state, code} to the API through the proxy (with the
// user's session) and go back to where they started. The state is checked server-side: single use, same user, 10 min.
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { errorText, post } from "@/lib/api";
import { safeNext } from "@/lib/nav";
import { Card, LinkButton, Notice } from "@/components/ui";
import { Logo } from "@/components/Logo";

function Inner() {
  const q = useSearchParams();
  const [msg, setMsg] = useState<{ tone: "info" | "danger" | "success"; text: string }>({ tone: "info", text: "Finishing the connection…" });
  const sent = useRef(false);
  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    const state = q.get("state") ?? "", code = q.get("code"), error = q.get("error");
    if (!state) { setMsg({ tone: "danger", text: "This link is missing its connection details. Start again from Settings." }); return; }
    post<{ return_to: string; connection: { account_label: string } }>("/v1/integrations/oauth/complete", { state, code, error })
      .then((r) => {
        setMsg({ tone: "success", text: `Connected ${r.connection.account_label}. Taking you back…` });
        const to = safeNext(r.return_to, "/start");
        setTimeout(() => location.replace(to), 800);
      })
      .catch((e) => setMsg({ tone: "danger", text: errorText(e) }));
    // remove code/state from the address bar and history
    history.replaceState(null, "", "/integrations/callback");
  }, [q]);
  return (
    <Card className="flex w-full max-w-md flex-col gap-4">
      <Notice tone={msg.tone}>{msg.text}</Notice>
      {msg.tone === "danger" && <LinkButton href="/start">Back to the app</LinkButton>}
    </Card>
  );
}

export default function Callback() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-4">
      <Logo />
      <Suspense fallback={<Card className="w-full max-w-md"><Notice>Finishing the connection…</Notice></Card>}><Inner /></Suspense>
    </main>
  );
}
