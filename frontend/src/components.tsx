import { useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { Check, ChevronLeft, ChevronRight, Package, X } from 'lucide-react';
import { display, type Row } from './api';

export interface Field {
  name: string;
  label: string;
  type?: string;
  options?: { value: string; label: string }[];
  required?: boolean;
  initial?: string;
  hint?: string;
}

/** Keep dialogs keyboard accessible and restore focus when closed. */
export function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const reference = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    reference.current?.showModal();
    return () => previous?.focus();
  }, []);
  return (
    <dialog
      ref={reference}
      onCancel={close}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
      aria-labelledby="dialog-title"
    >
      <div className="modal-head">
        <h2 id="dialog-title">{title}</h2>
        <button
          aria-label="Close dialog"
          className="icon-button"
          onClick={close}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

/** Render validated editable fields and prevent duplicate submissions. */
export function Form({
  fields,
  submit,
  label = 'Save changes',
}: {
  fields: Field[];
  submit: (values: Record<string, string>) => Promise<void>;
  label?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await submit(values as Record<string, string>);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save} className="form-grid">
      {fields.map((field) => (
        <label key={field.name}>
          {field.label}
          {field.options ? (
            <select name={field.name} defaultValue={field.initial}>
              {field.options.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          ) : field.type === 'textarea' ? (
            <textarea
              name={field.name}
              defaultValue={field.initial}
              required={field.required}
            />
          ) : (
            <input
              name={field.name}
              type={field.type || 'text'}
              defaultValue={field.initial}
              required={field.required}
              step={field.type === 'number' ? 'any' : undefined}
              autoComplete={
                field.type === 'password' ? 'new-password' : undefined
              }
            />
          )}
          {field.hint && <small>{field.hint}</small>}
        </label>
      ))}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <button className="primary" disabled={busy}>
        {busy ? 'Saving…' : label}
        <Check size={16} />
      </button>
    </form>
  );
}

/** Show consistent tables, row details, empty states and pagination. */
export function DataTable({
  rows,
  columns,
  select,
}: {
  rows: Row[];
  columns: [string, string][];
  select?: (row: Row) => void;
}) {
  if (!rows.length) {
    return (
      <div className="empty">
        <Package size={32} />
        <h3>No records yet</h3>
        <p>Your shop activity will appear here.</p>
      </div>
    );
  }
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map(([key, title]) => (
              <th key={key}>{title}</th>
            ))}
            {select && (
              <th>
                <span className="sr-only">Details</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={String(row.id || row.variant_id || index)}>
              {columns.map(([key]) => (
                <td key={key}>
                  {key === 'status' ? (
                    <span className={`badge ${String(row[key])}`}>
                      {display(row[key]).replaceAll('_', ' ')}
                    </span>
                  ) : key.endsWith('_at') ? (
                    new Date(String(row[key]) + 'Z').toLocaleString()
                  ) : (
                    display(row[key])
                  )}
                </td>
              ))}
              {select && (
                <td>
                  <button className="text-button" onClick={() => select(row)}>
                    View →
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Present bounded page navigation instead of silently truncating records. */
export function Pagination({
  offset,
  total,
  change,
}: {
  offset: number;
  total: number;
  change: (offset: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total ? offset + 1 : 0}–{Math.min(offset + 30, total)} of {total}
      </span>
      <div>
        <button
          className="icon-button"
          aria-label="Previous page"
          disabled={!offset}
          onClick={() => change(Math.max(0, offset - 30))}
        >
          <ChevronLeft size={18} />
        </button>
        <button
          className="icon-button"
          aria-label="Next page"
          disabled={offset + 30 >= total}
          onClick={() => change(offset + 30)}
        >
          <ChevronRight size={18} />
        </button>
      </div>
    </div>
  );
}

/** Display details as labelled values rather than raw implementation output. */
export function Details({ row }: { row: Row }) {
  return (
    <dl className="details">
      {Object.entries(row).map(([key, value]) => (
        <div key={key}>
          <dt>{key.replaceAll('_', ' ')}</dt>
          <dd>
            {Array.isArray(value) ? (
              value.map((item, i) => (
                <div key={i} className="detail-item">
                  {typeof item === 'object' && item ? (
                    <Details row={item as Row} />
                  ) : (
                    display(item)
                  )}
                </div>
              ))
            ) : value && typeof value === 'object' ? (
              <Details row={value as Row} />
            ) : (
              display(value)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}
