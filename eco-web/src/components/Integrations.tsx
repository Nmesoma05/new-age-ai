"use client";
// Connected accounts and the full integration catalog. Shows only what the API reports; never a token.
import { useState } from "react";
import { api, errorText, post, useApi } from "@/lib/api";
import { useWs } from "@/components/Shell";
import { Badge, Button, Card, ConfirmButton, Notice, SectionTitle, fmtDate, useToast } from "@/components/ui";

type CatalogItem = {
  key: string; name: string; vendor: string; category: string; access: "read" | "write" | "spend"; status: "implemented" | "planned";
  priority: number; docs_url: string; reads: string[]; writes: string[]; access_requirements: string[]; limits: string[];
  approval: string; fallback: string; connectable: boolean; configured: boolean; notes: string;
};
type Conn = {
  id: string; provider: string; name: string; status: string; account_label: string | null; scopes: string[];
  last_sync_at: string | null; last_error: string | null; last_error_at: string | null; consecutive_failures: number; connected_at: string;
};

const ACCESS: Record<string, [string, "success" | "warning" | "danger"]> = {
  read: ["Read-only", "success"], write: ["Posts or sends", "warning"], spend: ["Spends money", "danger"] };

export function SyncButton({ conn, onDone }: { conn: Conn; onDone?: () => void }) {
  const { ws, canWrite } = useWs();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return <Button size="sm" variant="secondary" loading={busy} disabled={!canWrite || conn.status !== "connected"} onClick={async () => {
    setBusy(true);
    try {
      const r = await post<{ videos: number; subscribers: number | null; note: string }>(`/v1/workspaces/${ws.id}/integrations/${conn.id}/sync`, {});
      toast(`Synced ${r.videos} video${r.videos === 1 ? "" : "s"} from YouTube`); onDone?.();
    } catch (e) { toast(errorText(e), "danger"); onDone?.(); } finally { setBusy(false); }
  }}>Sync now</Button>;
}

export function useConnections() {
  const { ws } = useWs();
  return useApi<{ connections: Conn[]; available: CatalogItem[] }>(`/v1/workspaces/${ws.id}/integrations`);
}

export default function Integrations() {
  const { ws, isAdmin, division, base } = useWs();
  const toast = useToast();
  const conns = useConnections();
  const cat = useApi<{ verified_on: string; implemented: CatalogItem[]; planned: CatalogItem[] }>(`/v1/integrations/catalog?product=${division.product}`);
  const [open, setOpen] = useState<string | null>(null);
  const connected = conns.data?.connections ?? [];

  async function connect(key: string) {
    try {
      const r = await post<{ authorization_url: string }>(`/v1/workspaces/${ws.id}/integrations/${key}/connect`, { return_to: `${base}/settings` });
      location.href = r.authorization_url;  // the provider's own consent page
    } catch (e) { toast(errorText(e), "danger"); }
  }

  return (
    <Card className="flex flex-col gap-5" id="integrations">
      <SectionTitle>Integrations</SectionTitle>
      <p className="text-[14px] text-muted">Read-only connections come first. Anything that would post, send or spend needs your approval each time, and none of those are built yet. Checked against providers' docs on {cat.data ? fmtDate(cat.data.verified_on, { day: "numeric", month: "short", year: "numeric" }) : "…"}.</p>

      <div>
        <h3 className="mb-2 text-[15px] font-semibold">Working now</h3>
        <ul className="flex flex-col gap-3">
          {cat.data?.implemented.map((i) => {
            const mine = connected.filter((c) => c.provider === i.key);
            return (
              <li key={i.key} className="rounded-m border border-line p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{i.name}</span>
                  <Badge tone={ACCESS[i.access][1]}>{ACCESS[i.access][0]}</Badge>
                  {!i.configured && <Badge tone="warning">Not set up on this server</Badge>}
                  {i.connectable && isAdmin && i.configured && mine.length === 0 &&
                    <Button size="sm" className="ml-auto" onClick={() => connect(i.key)}>Connect {i.name.split(" ")[0]}</Button>}
                </div>
                <p className="mt-1 text-[14px] text-muted">{i.notes || i.reads.join("; ")}</p>
                {!i.connectable && <p className="mt-1 text-[13px] text-muted">Shared service: no account to connect. {i.configured ? "" : "An operator has switched it off, so it falls back to: " + i.fallback}</p>}
                {mine.map((c) => (
                  <div key={c.id} className="mt-3 flex flex-col gap-2 rounded-m bg-sunken p-3 text-[14px]">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{c.account_label}</span>
                      {c.status === "connected" ? <Badge tone="success">Connected</Badge> : <Badge tone="danger">Needs reconnecting</Badge>}
                      <span className="text-muted">Last sync: {c.last_sync_at ? fmtDate(c.last_sync_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "never"}</span>
                      <span className="ml-auto flex gap-2">
                        <SyncButton conn={c} onDone={conns.reload} />
                        {isAdmin && c.status === "needs_reauth" && <Button size="sm" onClick={() => connect(i.key)}>Reconnect</Button>}
                        {isAdmin && <ConfirmButton label="Disconnect and delete our access?" onConfirm={async () => {
                          try { const r = await api.send<{ message: string; provider_confirmed: boolean | null }>("DELETE", `/v1/workspaces/${ws.id}/integrations/${c.id}`); toast(r.message, r.provider_confirmed ? "success" : "danger"); conns.reload(); }
                          catch (e) { toast(errorText(e), "danger"); }
                        }}>Disconnect</ConfirmButton>}
                      </span>
                    </div>
                    {c.last_error && <Notice tone="warning">{c.last_error}</Notice>}
                  </div>))}
              </li>);
          })}
        </ul>
        {!isAdmin && <p className="mt-2 text-[13px] text-muted">Only an organisation owner or admin can connect or disconnect accounts.</p>}
      </div>

      <div>
        <h3 className="mb-2 text-[15px] font-semibold">Planned (not available yet)</h3>
        <ul className="divide-y divide-line">
          {cat.data?.planned.map((i) => (
            <li key={i.key} className="py-2">
              <button className="flex w-full flex-wrap items-center gap-2 text-left" aria-expanded={open === i.key} onClick={() => setOpen(open === i.key ? null : i.key)}>
                <span className="font-semibold">{i.name}</span><Badge tone={ACCESS[i.access][1]}>{ACCESS[i.access][0]}</Badge>
                <span className="text-[13px] text-muted">{i.vendor}</span><span className="ml-auto text-[13px] text-muted">{open === i.key ? "Hide" : "What it needs"}</span>
              </button>
              {open === i.key && <div className="mt-2 flex flex-col gap-2 text-[14px]">
                {i.access_requirements.length > 0 && <div><span className="font-semibold">Before it can be built: </span>{i.access_requirements.join(" ")}</div>}
                {i.approval && <div><span className="font-semibold">Your approval: </span>{i.approval}</div>}
                <div><span className="font-semibold">Until then: </span>{i.fallback}</div>
                <a className="text-[13px] underline" href={i.docs_url} target="_blank" rel="noreferrer">Provider documentation</a>
              </div>}
            </li>))}
        </ul>
      </div>
    </Card>
  );
}
