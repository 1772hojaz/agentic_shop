import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Download, Plus, Search } from 'lucide-react';
import { api, type Identity, type Page, type Row } from './api';
import {
  DataTable,
  Details,
  Form,
  Modal,
  Pagination,
  type Field,
} from './components';

import { CONFIG, ORDER_STATES } from './resource-config';
import { creation, exportCsv } from './resource-forms';
import { RowActions } from './ResourceActions';
import { ImageUpload } from './ImageUpload';

export type Perform = (
  path: string,
  method: string,
  body?: unknown,
) => Promise<Row>;
interface ResourceProps {
  name: string;
  identity: Identity;
  perform: Perform;
  revision: number;
  navigate: (name: string) => void;
}

/** Load each resource from its real API and expose permitted business actions. */
export function Resources(props: ResourceProps) {
  const { name, identity, perform, revision, navigate } = props;
  const config = CONFIG[name];
  const [records, setRecords] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const [modal, setModal] = useState<{ title: string; content: ReactNode }>();
  const [refresh, setRefresh] = useState(0);
  const editable = Boolean(
    config.permission && identity.permissions.includes(config.permission),
  );
  function reload() {
    setModal(undefined);
    setRefresh((value) => value + 1);
  }
  useEffect(() => {
    let active = true;
    setBusy(true);
    setError('');
    const params = new URLSearchParams({
      offset: String(offset),
      limit: '30',
      query,
    });
    if (status) params.set('status', status);
    api<Page | Row[]>(`${config.path}?${params}`)
      .then((result) => {
        if (!active) return;
        const rows = Array.isArray(result) ? result : result.items;
        setRecords(rows);
        setTotal(
          Array.isArray(result) ? rows.length : (result.total ?? rows.length),
        );
      })
      .catch((failure) => {
        if (active) setError(failure.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [config.path, offset, query, status, refresh, revision]);
  function openForm(
    title: string,
    fields: Field[],
    save: (values: Record<string, string>) => Promise<unknown>,
  ) {
    setModal({
      title,
      content: (
        <Form
          fields={fields}
          submit={async (values) => {
            await save(values);
            reload();
          }}
        />
      ),
    });
  }
  async function view(row: Row) {
    try {
      const suffix =
        name === 'Orders' ||
        name === 'Customers' ||
        name === 'WhatsApp Conversations';
      const detail = suffix
        ? await api<Row | Page>(`${config.path}/${row.id}`)
        : row;
      setModal({
        title: `${name} details`,
        content: (
          <>
            <RowActions
              name={name}
              row={row}
              identity={identity}
              perform={perform}
              openForm={openForm}
              reload={reload}
            />
            <Details row={detail as Row} />
          </>
        ),
      });
    } catch (failure) {
      setError((failure as Error).message);
    }
  }
  async function create() {
    const definition = creation(name, perform);
    if (!definition) return;
    let fields: Field[] = definition.fields;
    if (name === 'Products') {
      try {
        const categories = await api<Page>('/categories');
        fields = fields.map((field) =>
          field.name === 'category_id'
            ? {
                ...field,
                label: 'Category',
                options: [
                  { value: '', label: 'Uncategorised' },
                  ...categories.items.map((item) => ({
                    value: String(item.id),
                    label: String(item.name),
                  })),
                ],
              }
            : field,
        );
      } catch (failure) {
        setError((failure as Error).message);
        return;
      }
    }
    openForm(`Add ${name.toLowerCase()}`, fields, definition.save);
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">SHOP WORKSPACE</div>
          <h1>{name}</h1>
          <p>{config.description}</p>
        </div>
        <div className="button-row">
          {name === 'Inventory' && (
            <button
              className="secondary"
              onClick={() => navigate('Stock Movements')}
            >
              Stock history
            </button>
          )}
          {editable &&
            ['Products', 'Categories', 'Staff', 'Notifications'].includes(
              name,
            ) && (
              <button className="primary" onClick={create}>
                <Plus size={17} />
                {name === 'Notifications'
                  ? 'Send notification'
                  : 'Add ' +
                    name.toLowerCase().replace(/ies$/, 'y').replace(/s$/, '')}
              </button>
            )}
        </div>
      </div>
      <section className="panel">
        <div className="table-toolbar">
          <label className="search-input">
            <Search size={17} />
            <input
              aria-label={`Search ${name}`}
              placeholder={`Search ${name.toLowerCase()}…`}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setOffset(0);
              }}
            />
          </label>
          {name === 'Orders' && (
            <select
              aria-label="Filter order status"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">All statuses</option>
              {ORDER_STATES.map((state) => (
                <option key={state} value={state}>
                  {state.replaceAll('_', ' ')}
                </option>
              ))}
            </select>
          )}
          <button
            className="secondary"
            disabled={!records.length}
            onClick={() => exportCsv(name, records)}
          >
            <Download size={15} />
            Export page
          </button>
        </div>
        {error ? (
          <div className="error" role="alert">
            {error}
            <button onClick={() => setRefresh((value) => value + 1)}>
              Retry
            </button>
          </div>
        ) : busy ? (
          <div className="loading" role="status">
            Loading {name.toLowerCase()}…
          </div>
        ) : (
          <DataTable rows={records} columns={config.columns} select={view} />
        )}
        <Pagination offset={offset} total={total} change={setOffset} />
      </section>
      {name === 'Products' && editable && <ImageUpload />}
      {modal && (
        <Modal title={modal.title} close={() => setModal(undefined)}>
          {modal.content}
        </Modal>
      )}
    </>
  );
}
