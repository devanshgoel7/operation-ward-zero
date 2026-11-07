import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";

const icons = {
  mark: <><path d="M12 3v6m0 6v6M3 12h6m6 0h6"/><circle cx="12" cy="12" r="2.5"/></>,
  overview: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  patients: <><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2M16 5a3 3 0 0 1 0 6m1 3a4 4 0 0 1 4 4v2"/></>,
  alert: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12a2 2 0 0 0 4 0"/></>,
  history: <><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1m-6 7h6m-6 5h6"/></>,
  pulse: <path d="M3 12h4l3-7 4 14 3-7h4"/>,
  caregiver: <><circle cx="12" cy="8" r="3"/><path d="M5 20v-2a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v2"/></>,
  search: <><circle cx="10.5" cy="10.5" r="5.5"/><path d="m15 15 5 5"/></>,
  menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
  close: <path d="m6 6 12 12M18 6 6 18"/>,
  refresh: <><path d="M20 11a8 8 0 1 0-2 6m2-12v6h-6"/></>,
  arrow: <path d="M5 12h14m-6-6 6 6-6 6"/>,
  check: <path d="m5 12 4 4L19 6"/>,
  clock: <><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></>,
} satisfies Record<string, ReactNode>;

type IconName = keyof typeof icons;

export function Icon({ name }: { name: IconName }) {
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icons[name]}</svg>;
}

const navigation = [
  { target: "monitoring", label: "Overview", icon: "overview" },
  { target: "patients", label: "Patients", icon: "patients" },
  { target: "vital-signs", label: "Vital signs", icon: "pulse" },
  { target: "patient-context", label: "History and observations", icon: "history" },
  { target: "caregiver-inbox", label: "Caregiver inbox", icon: "alert" },
  { target: "system-health", label: "System health", icon: "pulse" },
] as const;

type Section = typeof navigation[number]["target"];

function sectionFromHash() {
  const hash = location.hash.slice(1);
  const target = hash === "record-observation" ? "patient-context" : hash;
  return navigation.find(item => item.target === target)?.target;
}

function Sidebar() {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<Section>(() => sectionFromHash() ?? "monitoring");
  const jumpPosition = useRef<number | undefined>(undefined);
  const jumpFrame = useRef(0);

  useEffect(() => {
    const sections = navigation.map(({ target }) => ({ target, element: document.getElementById(target) })).reverse();
    let frame = 0;

    function updateFromScroll() {
      frame = 0;
      const top = window.scrollY;
      if (jumpPosition.current === top) return;
      jumpPosition.current = undefined;
      const height = window.innerHeight;
      const remaining = document.documentElement.scrollHeight - height - top;
      // Lower the reading line on the last screen so short sections can become active.
      const readingLine = top > 0 ? Math.max(Math.min(96, height * .2), height - remaining) : 0;
      const current = sections.find(({ element }) => element && element.getBoundingClientRect().top <= readingLine);
      setActive(current?.target ?? "monitoring");
    }

    function schedule() {
      if (!frame) frame = requestAnimationFrame(updateFromScroll);
    }

    function followHash() {
      const target = sectionFromHash();
      // A jump near the end can be clamped. Keep its explicit selection until scrolling resumes.
      jumpPosition.current = target ? window.scrollY : undefined;
      if (target) setActive(target);
      else schedule();
    }

    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    window.addEventListener("hashchange", followHash);
    const observer = new ResizeObserver(schedule);
    const main = document.getElementById("monitoring");
    if (main) observer.observe(main);
    followHash();
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("hashchange", followHash);
      observer.disconnect();
      cancelAnimationFrame(frame);
      cancelAnimationFrame(jumpFrame.current);
    };
  }, []);

  function followLink(event: MouseEvent<HTMLAnchorElement>, target: Section) {
    setOpen(false);
    if (location.hash !== `#${target}` || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    // Repeating a link still jumps, but the browser emits no hashchange.
    cancelAnimationFrame(jumpFrame.current);
    jumpFrame.current = requestAnimationFrame(() => {
      jumpPosition.current = window.scrollY;
      setActive(target);
    });
  }

  return <aside className="sidebar">
    <div className="sidebar-top">
      <a className="brand" href="#monitoring" onClick={event => followLink(event, "monitoring")}>
        <span className="brand-mark"><Icon name="mark"/></span>
        <span>Operation Ward Zero<small>Monitoring workspace</small></span>
      </a>
      <button className="menu-toggle icon-button" type="button" aria-label={open ? "Close navigation" : "Open navigation"}
        aria-expanded={open} aria-controls="dashboard-navigation" onClick={() => setOpen(!open)}>
        <Icon name={open ? "close" : "menu"}/>
      </button>
    </div>
    <nav className="sidebar-nav" id="dashboard-navigation" aria-label="Dashboard navigation" data-open={open}>
      <p className="nav-caption">Workspace</p>
      {navigation.map(({ target, label, icon }) => <a key={target} href={`#${target}`}
        aria-current={active === target ? "location" : undefined} onClick={event => followLink(event, target)}>
        <Icon name={icon}/><span>{label}</span>
      </a>)}
    </nav>
    <div className="sidebar-foot"><span className="demo-dot"/> Synthetic demo workspace</div>
  </aside>;
}

export function DashboardHeader({ search, onSearch, caregivers, actor, onActorChange }: {
  search: string; onSearch: (search: string) => void; caregivers: { id: string; display_name: string }[];
  actor: string; onActorChange: (actor: string) => void;
}) {
  return <header className="topbar">
    <form className="patient-search" role="search" aria-label="Patient roster" onSubmit={event => {
      event.preventDefault();
      if (location.hash !== "#patients") location.hash = "patients";
      document.getElementById("patients")?.focus();
    }}>
      <Icon name="search"/>
      <input id="patient-search-input" type="search" aria-label="Search patients" placeholder="Search patients…" value={search}
        onChange={event => onSearch(event.target.value)}/>
      {search && <button className="icon-button" type="button" aria-label="Clear patient search" onClick={() => {
        const input = document.getElementById("patient-search-input");
        onSearch("");
        input?.focus();
      }}><Icon name="close"/></button>}
    </form>
    <div className="topbar-tools">
      <a className="inbox-shortcut" href="#caregiver-inbox"><Icon name="alert"/> Caregiver inbox</a>
      <label className="caregiver-picker"><span className="caregiver-icon"><Icon name="caregiver"/></span>
        <span>Demo caregiver</span>
        <select value={actor} disabled={!caregivers.length} onChange={event => onActorChange(event.target.value)}>
          {!caregivers.length && <option value="">Unavailable</option>}
          {caregivers.map(caregiver => <option key={caregiver.id} value={caregiver.id}>{caregiver.display_name}</option>)}
        </select>
      </label>
    </div>
  </header>;
}

export function DashboardShell({ header, children }: { header: ReactNode; children: ReactNode }) {
  return <div className="dashboard-shell">
    <a className="skip-link" href="#monitoring">Skip to patient monitoring</a>
    <Sidebar/>
    <div className="workspace">
      {header}
      <main id="monitoring" tabIndex={-1}>{children}</main>
    </div>
  </div>;
}

export function Panel({ id, title, description, action, className, children }: {
  id: string; title: string; description?: string; action?: ReactNode; className?: string; children: ReactNode;
}) {
  return <section id={id} className={className ? `panel ${className}` : "panel"} aria-labelledby={`${id}-heading`} tabIndex={-1}>
    <div className="panel-heading">
      <div><h2 id={`${id}-heading`}>{title}</h2>{description && <p>{description}</p>}</div>
      {action}
    </div>
    {children}
  </section>;
}

export function StatusBadge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className="status-badge" data-tone={tone}><span aria-hidden="true"/>{children}</span>;
}

export function MetricCard({ label, value, detail, icon, accent }: {
  label: string; value: number | undefined; detail: string; icon: IconName; accent: "orange" | "mint" | "lavender" | "blue";
}) {
  return <article className="metric-card" aria-label={label}>
    <div className="metric-label"><span className="metric-icon" data-accent={accent}><Icon name={icon}/></span><h2>{label}</h2></div>
    <p className="metric-value">{value ?? "—"}</p>
    <p className="metric-detail">{detail}</p>
  </article>;
}
