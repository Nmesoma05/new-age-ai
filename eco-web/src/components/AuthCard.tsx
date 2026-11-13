import { Logo } from "./Logo";

export function AuthFrame({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <section className="hidden flex-col justify-between bg-sidebar p-10 text-sidebar-ink lg:flex">
        <Logo inverse tagline />
        <div>
          <h2 className="font-display text-[40px] font-bold leading-[44px] tracking-[-0.8px]">AI that works the way you work.</h2>
          <p className="mt-4 max-w-[46ch] text-[17px] leading-[26px] text-sidebar-muted">
            For creators and agencies managing clients, businesses planning their own marketing, and freelancers
            and job seekers growing their careers. Every workspace is kept separate. The AI drafts; you decide what goes out.
          </p>
        </div>
        <p className="text-[13px] text-sidebar-muted">Nothing is posted, sent or paid for you. You act, then record the results.</p>
      </section>
      <section className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden"><Logo tagline /></div>
          <h1 className="font-display text-[28px] font-[650] leading-[34px]">{title}</h1>
          <p className="mt-1 text-muted">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>
      </section>
    </div>
  );
}
