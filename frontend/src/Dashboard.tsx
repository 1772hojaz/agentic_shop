import { useEffect, useState } from 'react';
import {
  ArrowUpRight,
  Box,
  CircleDollarSign,
  ShoppingBag,
  Users,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api, money, type Page, type Row } from './api';
import { DataTable } from './components';

interface Report {
  revenue: string;
  total_orders: number;
  customers: number;
  products: number;
  low_stock: number;
  average_order_value: string;
  order_statuses: Record<string, number>;
  trend: Row[];
  best_sellers: Row[];
  category_sales: Row[];
  customer_activity: Row[];
}

/** Show authoritative sales, inventory signals and recent orders. */
export function Dashboard({
  currency,
  navigate,
  view = 'Dashboard',
}: {
  currency: string;
  navigate: (page: string) => void;
  view?: string;
}) {
  const [report, setReport] = useState<Report>();
  const [orders, setOrders] = useState<Row[]>([]);
  const [error, setError] = useState('');
  const [days, setDays] = useState('30');
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Report>(`/reports/sales?days=${days}`),
      api<Page>('/orders?limit=5'),
    ])
      .then(([metrics, recent]) => {
        if (active) {
          setReport(metrics);
          setOrders(recent.items);
        }
      })
      .catch((failure) => {
        if (active) setError(failure.message);
      });
    return () => {
      active = false;
    };
  }, [days]);
  if (error)
    return (
      <div className="error" role="alert">
        {error}
      </div>
    );
  if (!report)
    return (
      <div className="loading" role="status">
        Loading your shop overview…
      </div>
    );
  const cards = [
    {
      title: 'Total revenue',
      value: money(report.revenue, currency),
      icon: CircleDollarSign,
      note: 'Verified payments',
    },
    {
      title: 'Orders received',
      value: report.total_orders,
      icon: ShoppingBag,
      note: `${report.order_statuses.pending_payment || 0} awaiting payment`,
    },
    {
      title: 'Customers',
      value: report.customers,
      icon: Users,
      note: 'Across your shop',
    },
    {
      title: 'Active products',
      value: report.products,
      icon: Box,
      note: `${report.low_stock} variants running low`,
    },
  ];
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR BUSINESS, AT A GLANCE</div>
          <h1>{view === 'Dashboard' ? 'Shop overview' : view}</h1>
          <p>A clear view of what’s happening in your shop.</p>
        </div>
        <select
          aria-label="Report period"
          value={days}
          onChange={(event) => setDays(event.target.value)}
        >
          <option value="1">Last 24 hours</option>
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
          <option value="90">Last 90 days</option>
        </select>
      </div>
      <div className="stats">
        {cards.map(({ title, value, icon: Icon, note }) => (
          <section className="stat" key={title}>
            <div className="stat-label">
              {title}
              <span>
                <Icon size={18} />
              </span>
            </div>
            <strong>{value}</strong>
            <small>{note}</small>
          </section>
        ))}
      </div>
      <div className="chart-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Revenue performance</h2>
              <p>Payments received over the selected period</p>
            </div>
            <span className="legend">
              <i />
              Revenue
            </span>
          </div>
          {report.trend.length ? (
            <div className="chart">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={report.trend}>
                  <defs>
                    <linearGradient id="revenue" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor="#259b76"
                        stopOpacity={0.22}
                      />
                      <stop
                        offset="100%"
                        stopColor="#259b76"
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="3 5"
                    vertical={false}
                    stroke="#e6ebe7"
                  />
                  <XAxis
                    dataKey="date"
                    tickLine={false}
                    axisLine={false}
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis
                    tickLine={false}
                    axisLine={false}
                    tick={{ fontSize: 11 }}
                  />
                  <Tooltip
                    formatter={(value: number) => money(value, currency)}
                  />
                  <Area
                    dataKey="revenue"
                    type="monotone"
                    stroke="#198562"
                    strokeWidth={2.5}
                    fill="url(#revenue)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="chart-empty">
              <CircleDollarSign size={32} />
              <strong>Your next chapter starts with a sale</strong>
              <p>Verified payments will build your revenue chart.</p>
            </div>
          )}
        </section>
        <section className="panel operations">
          <span className="eyebrow">KEEP THINGS MOVING</span>
          <h2>
            A little attention,
            <br />a smoother shop.
          </h2>
          <div className="operation-row">
            <span>Awaiting payment</span>
            <strong>{report.order_statuses.pending_payment || 0}</strong>
          </div>
          <div className="operation-row">
            <span>Orders processing</span>
            <strong>{report.order_statuses.processing || 0}</strong>
          </div>
          <div className="operation-row">
            <span>Low-stock variants</span>
            <strong>{report.low_stock}</strong>
          </div>
          <button
            onClick={() => navigate('Inventory')}
            className="text-button"
          >
            Review inventory <ArrowUpRight size={16} />
          </button>
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Recent orders</h2>
            <p>The latest activity from your customers</p>
          </div>
          <button className="text-button" onClick={() => navigate('Orders')}>
            View all orders <ArrowUpRight size={16} />
          </button>
        </div>
        <DataTable
          rows={orders.map((row) => ({
            ...row,
            id: String(row.id).slice(0, 8).toUpperCase(),
            total: money(row.total, currency),
          }))}
          columns={[
            ['id', 'Order'],
            ['created_at', 'Placed'],
            ['status', 'Status'],
            ['total', 'Total'],
          ]}
        />
      </section>
      {view !== 'Dashboard' && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>
                {view === 'Analytics'
                  ? 'Customer purchasing activity'
                  : 'Best-selling products'}
              </h2>
              <p>
                Paid orders in the selected period · Average order value{' '}
                {money(report.average_order_value, currency)}
              </p>
            </div>
          </div>
          <DataTable
            rows={
              view === 'Analytics'
                ? report.customer_activity
                : report.best_sellers
            }
            columns={
              view === 'Analytics'
                ? [
                    ['name', 'Customer'],
                    ['orders', 'Orders'],
                    ['spend', 'Spend'],
                  ]
                : [
                    ['name', 'Product'],
                    ['units', 'Units'],
                    ['sales', 'Sales'],
                  ]
            }
          />
        </section>
      )}
      {view !== 'Dashboard' && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Sales by category</h2>
              <p>
                Completion rate:{' '}
                {report.total_orders
                  ? Math.round(
                      ((report.order_statuses.completed || 0) /
                        report.total_orders) *
                        100,
                    )
                  : 0}
                % of orders · {report.order_statuses.cancelled || 0} cancelled
              </p>
            </div>
          </div>
          <DataTable
            rows={report.category_sales}
            columns={[
              ['category', 'Category'],
              ['units', 'Units'],
              ['sales', 'Sales'],
            ]}
          />
        </section>
      )}
    </>
  );
}
