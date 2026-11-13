"use client";
import { useState } from "react";
import { errorText, patch, post, useApi } from "@/lib/api";
import type { Capability } from "@/lib/types";
import { platformLabel } from "@/lib/types";
import { useWs } from "@/components/Shell";
import Integrations from "@/components/Integrations";
import ChangePassword from "@/components/ChangePassword";
import YourData from "@/components/YourData";
import { Button, Card, Field, Input, Notice, PageHeader, SectionTitle, Select, StatusBadge, useToast } from "@/components/ui";

type Caps = { features: Capability[]; platforms?: { platform: string; publishing: string; analytics: string; manual_tracking: string }[] };
type Member = { user_id: string; display_name: string; email: string; role: string };

export default function Settings() {
  const { ws, isAdmin, division } = useWs();
  const toast = useToast();
  const caps = useApi<Caps>(division.capabilitiesUrl);
  const wsMembers = useApi<{ user_id: string; role: string }[]>(`/v1/workspaces/${ws.id}/members`);
  const orgMembers = useApi<Member[]>(`/v1/orgs/${ws.org_id}/members`);
  const [name, setName] = useState(ws.name);
  const [add, setAdd] = useState({ user_id: "", role: "editor" });
  const person = (id: string) => orgMembers.data?.find((m) => m.user_id === id);
  const addable = (orgMembers.data ?? []).filter((m) => !["owner", "admin"].includes(m.role) && !wsMembers.data?.some((w) => w.user_id === m.user_id));
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Settings" description={`What works today, who can access this ${division.noun}, and the workspace name.`} />
      <Card>
        <SectionTitle>What works today</SectionTitle>
        <p className="mb-4 text-[14px] text-muted">{division.product === "business"
          ? "Some features need a connection to an ad account, CRM or messaging service. Those aren't built yet, so nothing is launched, paid or sent: you do it, then record the results."
          : division.product === "freelancer"
          ? "Remotive job listings and exchange rates work now. Applying, messaging clients and other job boards aren't connected: you do those yourself and track them here."
          : "Publishing needs a connection to each platform. Those aren't built yet, so the app never pretends: you post, then record it. YouTube analytics can be connected below (read-only)."}</p>
        <ul className="divide-y divide-line">
          {caps.data?.features.map((f) => (
            <li key={f.feature} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-start sm:gap-4">
              <div className="w-56 shrink-0 font-semibold">{f.feature}</div>
              <div className="flex-1 text-[14px] text-muted">{f.detail}</div>
              <StatusBadge status={f.status} />
            </li>))}
        </ul>
      </Card>
      <Integrations />
      {caps.data?.platforms && <Card>
        <SectionTitle>Platform connections</SectionTitle>
        <div className="overflow-x-auto"><table className="w-full text-[14px]">
          <thead className="bg-sunken text-left text-[13px]"><tr><th className="p-2">Platform</th><th className="p-2">Publishing</th><th className="p-2">Analytics</th><th className="p-2">Manual tracking</th></tr></thead>
          <tbody>{caps.data?.platforms.map((p) => (
            <tr key={p.platform} className="border-t border-line"><td className="p-2 font-semibold">{platformLabel(p.platform)}</td>
              <td className="p-2"><StatusBadge status={p.publishing} /></td><td className="p-2"><StatusBadge status={p.analytics} /></td><td className="p-2"><StatusBadge status={p.manual_tracking} /></td></tr>))}</tbody>
        </table></div>
      </Card>}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="flex flex-col gap-4">
          <SectionTitle>Workspace</SectionTitle>
          <Field label="Workspace name" htmlFor="wn"><Input id="wn" disabled={!isAdmin} value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <div><Button disabled={!isAdmin || !name.trim() || name === ws.name} onClick={async () => {
            try { await patch(`/v1/workspaces/${ws.id}`, { name }); toast("Renamed"); location.reload(); } catch (e) { toast(errorText(e), "danger"); }
          }}>Rename</Button></div>
          <p className="text-[14px]">Your role here: <span className="font-semibold">{ws.role}</span></p>
        </Card>
        <Card className="flex flex-col gap-4">
          <SectionTitle>People with access</SectionTitle>
          <p className="text-[14px] text-muted">{`Organisation owners and admins can see every ${division.noun}. Add team members here to give them access to this ${division.noun} only.`}</p>
          <ul className="divide-y divide-line">
            {orgMembers.data?.filter((m) => ["owner", "admin"].includes(m.role)).map((m) => (
              <li key={m.user_id} className="flex justify-between py-2 text-[14px]"><span>{m.display_name} <span className="text-muted">{m.email}</span></span><span className="text-muted">org {m.role}</span></li>))}
            {wsMembers.data?.map((w) => (
              <li key={w.user_id} className="flex justify-between py-2 text-[14px]"><span>{person(w.user_id)?.display_name ?? "Team member"} <span className="text-muted">{person(w.user_id)?.email}</span></span><span>{w.role}</span></li>))}
          </ul>
          {isAdmin && addable.length > 0 && (
            <div className="flex flex-wrap items-end gap-2">
              <Field label="Add" htmlFor="am"><Select id="am" value={add.user_id} onChange={(e) => setAdd({ ...add, user_id: e.target.value })}>
                <option value="">Choose a team member</option>{addable.map((m) => <option key={m.user_id} value={m.user_id}>{m.display_name}</option>)}</Select></Field>
              <Field label="Role" htmlFor="ar"><Select id="ar" value={add.role} onChange={(e) => setAdd({ ...add, role: e.target.value })}>
                <option value="admin">Admin (can approve)</option><option value="editor">Editor</option><option value="viewer">Viewer</option></Select></Field>
              <Button disabled={!add.user_id} onClick={async () => {
                try { await post(`/v1/workspaces/${ws.id}/members`, add); toast("Access given"); wsMembers.reload(); setAdd({ user_id: "", role: "editor" }); }
                catch (e) { toast(errorText(e), "danger"); }
              }}>Add</Button>
            </div>
          )}
          {isAdmin && addable.length === 0 && <Notice>To add someone new, first add them to your organisation (team plans).</Notice>}
        </Card>
      </div>
      <ChangePassword />
      <YourData />
    </div>
  );
}
