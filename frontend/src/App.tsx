import { lazy, Suspense, useEffect, useState } from 'react';
import {
  Activity,
  Bell,
  Bot,
  Boxes,
  ChevronDown,
  CircleHelp,
  ClipboardList,
  Folder,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageCircle,
  Settings as SettingsIcon,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  TrendingUp,
  Users,
  X,
} from 'lucide-react';
import { api, setCsrf, type Identity, type Pending, type Row } from './api';
import { Login } from './Login';
import { Details, Modal } from './components';
const Agent = lazy(() =>
  import('./Agent').then((m) => ({ default: m.Agent })),
);
const Settings = lazy(() =>
  import('./Settings').then((m) => ({ default: m.Settings })),
);

const Dashboard = lazy(() =>
  import('./Dashboard').then((m) => ({ default: m.Dashboard })),
);
const Resources = lazy(() =>
  import('./Resources').then((m) => ({ default: m.Resources })),
);

const NAVIGATION = [
  {
    group: 'WORKSPACE',
    items: [
      { name: 'Dashboard', icon: LayoutDashboard, permission: 'reports.read' },
    ],
  },
  {
    group: 'COMMERCE',
    items: [
      { name: 'Products', icon: ShoppingBag, permission: 'products.read' },
      { name: 'Categories', icon: Folder, permission: 'products.read' },
      { name: 'Inventory', icon: Boxes, permission: 'inventory.read' },
      { name: 'Orders', icon: ClipboardList, permission: 'orders.read' },
      { name: 'Customers', icon: Users, permission: 'customers.read' },
    ],
  },
  {
    group: 'BUSINESS INTELLIGENCE',
    items: [
      { name: 'Sales Reports', icon: TrendingUp, permission: 'reports.read' },
      { name: 'Analytics', icon: Activity, permission: 'reports.read' },
    ],
  },
  {
    group: 'COMMUNICATION',
    items: [
      {
        name: 'WhatsApp Conversations',
        icon: MessageCircle,
        permission: 'ai.read',
      },
      { name: 'Notifications', icon: Bell, permission: 'notifications.write' },
    ],
  },
  {
    group: 'ADMINISTRATION',
    items: [
      { name: 'Staff', icon: Users, permission: 'staff.write' },
      {
        name: 'Roles and Permissions',
        icon: ShieldCheck,
        permission: 'staff.write',
      },
      { name: 'AI Agent', icon: Bot, permission: 'ai.chat' },
      { name: 'Settings', icon: SettingsIcon, permission: 'settings.write' },
      { name: 'Audit Log', icon: ClipboardList, permission: 'audit.read' },
    ],
  },
];

/** Resolve authentication and compose the shared administration workspace. */
export default function App() {
  const [identity, setIdentity] = useState<Identity>();
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState('Dashboard');
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState<Pending>();
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');
  const [mobile, setMobile] = useState(false);
  const [currency, setCurrency] = useState('USD');
  useEffect(() => {
    api<Identity>('/auth/me')
      .then(acceptIdentity)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(''), 5000);
    return () => window.clearTimeout(timer);
  }, [toast]);
  function acceptIdentity(value: Identity) {
    setCsrf(value.csrf_token);
    setIdentity(value);
    if (!value.permissions.includes('reports.read')) {
      const first = NAVIGATION.flatMap((group) => group.items).find((item) =>
        value.permissions.includes(item.permission),
      );
      setPage(first?.name || 'AI Agent');
    }
    api<Row>('/shop')
      .then((result) => setCurrency(String(result.currency)))
      .catch(() => {});
  }
  function navigate(name: string) {
    setPage(name);
    setMobile(false);
    setError('');
  }
  async function perform(
    path: string,
    method: string,
    body?: unknown,
  ): Promise<Row> {
    const result = await api<Row>(path, method, body);
    if (result.confirmation_required) setPending(result as unknown as Pending);
    else {
      setRevision((value) => value + 1);
      setToast('Your changes are saved.');
    }
    return result;
  }
  async function approve() {
    if (!pending) return;
    setError('');
    try {
      await perform(`/confirmations/${pending.id}/confirm`, 'POST');
      setPending(undefined);
    } catch (failure) {
      setError((failure as Error).message);
    }
  }
  if (loading)
    return <div className="app-loading">Opening your shop workspace…</div>;
  if (!identity) return <Login accept={acceptIdentity} />;
  return (
    <div className="app-shell">
      {mobile && (
        <button
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <aside className={`sidebar ${mobile ? 'open' : ''}`}>
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            navigate('Dashboard');
          }}
        >
          <span className="brand-mark">
            <ShoppingBag size={21} />
          </span>
          <div>
            agentic<span>SHOP WORKSPACE</span>
          </div>
        </a>
        <div className="shop-switch">
          <span className="shop-avatar">AS</span>
          <div>
            <strong>Agentic Shop</strong>
            <small>Commerce administration</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <nav aria-label="Main navigation">
          {NAVIGATION.map((group) => {
            const items = group.items.filter((item) =>
              identity.permissions.includes(item.permission),
            );
            return items.length ? (
              <div className="nav-group" key={group.group}>
                <span>{group.group}</span>
                {items.map(({ name, icon: Icon }) => (
                  <button
                    className={page === name ? 'active' : ''}
                    aria-current={page === name ? 'page' : undefined}
                    key={name}
                    onClick={() => navigate(name)}
                  >
                    <Icon size={17} />
                    <span>{name}</span>
                    {name === 'AI Agent' && (
                      <Sparkles size={13} className="nav-sparkle" />
                    )}
                  </button>
                ))}
              </div>
            ) : null;
          })}
        </nav>
        <div className="sidebar-footer">
          <ShieldCheck size={17} />
          <p>
            One connected workspace.
            <br />
            <span>Every action, permission checked.</span>
          </p>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            <button
              className="icon-button menu-toggle"
              onClick={() => setMobile(true)}
              aria-label="Open navigation"
            >
              <Menu size={21} />
            </button>
            <span className="breadcrumb">
              Workspace <span>/</span> <strong>{page}</strong>
            </span>
          </div>
          <div className="topbar-actions">
            <a
              className="icon-button"
              href="/docs"
              target="_blank"
              rel="noreferrer"
              aria-label="API documentation"
            >
              <CircleHelp size={19} />
            </a>
            <div className="user-avatar">
              {identity.name.slice(0, 1).toUpperCase()}
            </div>
            <span className="account-name">{identity.name}</span>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={() =>
                api('/auth/logout', 'POST')
                  .then(() => {
                    setIdentity(undefined);
                    setCsrf('');
                  })
                  .catch((failure) => setError(failure.message))
              }
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <main>
          <Suspense
            fallback={<div className="loading">Opening workspace…</div>}
          >
            {error && !pending && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
            {['Dashboard', 'Sales Reports', 'Analytics'].includes(page) ? (
              <Dashboard
                key={`${page}-${revision}`}
                currency={currency}
                navigate={navigate}
                view={page}
              />
            ) : page === 'AI Agent' ? (
              <Agent perform={perform} revision={revision} />
            ) : page === 'Settings' ? (
              <Settings perform={perform} revision={revision} />
            ) : (
              <Resources
                key={page}
                name={page}
                identity={identity}
                perform={perform}
                revision={revision}
                navigate={navigate}
              />
            )}
            <footer className="page-footer">
              <span>Agentic Shop</span>
              <span>Built for the way your business works.</span>
            </footer>
          </Suspense>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <ShieldCheck size={18} />
          {toast}
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast('')}
          >
            <X size={15} />
          </button>
        </div>
      )}
      {pending && (
        <Modal
          title="Review and confirm"
          close={() => {
            setPending(undefined);
            setError('');
          }}
        >
          <p className="muted">
            You are approving this exact operation. No changes are made until
            you confirm.
          </p>
          <h3>{pending.action.replaceAll('_', ' ')}</h3>
          <Details row={pending.payload} />
          <p className="muted">
            Expires: {new Date(pending.expires_at + 'Z').toLocaleTimeString()}
          </p>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <div className="button-row">
            <button
              className="secondary"
              onClick={() => setPending(undefined)}
            >
              Go back
            </button>
            <button className="primary" onClick={() => void approve()}>
              Confirm operation
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
