/** Same-origin API transport with revocable cookies and CSRF protection. */
let csrfToken = '';

export type Row = Record<string, unknown>;
export interface Page {
  items: Row[];
  total?: number;
}
export interface Identity {
  id: string;
  name: string;
  context: string;
  permissions: string[];
  csrf_token: string;
}
export interface Pending {
  confirmation_required: boolean;
  id: string;
  action: string;
  payload: Row;
  expires_at: string;
}

/** Update the in-memory CSRF token without persisting authentication data. */
export function setCsrf(value: string): void {
  csrfToken = value;
}

/** Fetch JSON and normalize server validation errors into readable messages. */
export async function api<T>(
  path: string,
  method = 'GET',
  data?: unknown,
): Promise<T> {
  const form = data instanceof FormData;
  const response = await fetch('/api/v1' + path, {
    method,
    credentials: 'same-origin',
    headers: {
      ...(!form && data !== undefined
        ? { 'Content-Type': 'application/json' }
        : {}),
      'X-CSRF-Token': csrfToken,
    },
    body: data === undefined ? undefined : form ? data : JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) {
    const fields = result.fields
      ?.map(
        (item: { field: string; message: string }) =>
          `${item.field}: ${item.message}`,
      )
      .join('; ');
    throw new Error(fields || result.detail || 'The request failed.');
  }
  return result as T;
}

/** Format currency using the configured shop currency. */
export function money(value: unknown, currency = 'USD'): string {
  return new Intl.NumberFormat('en', {
    style: 'currency',
    currency,
  }).format(Number(value || 0));
}

/** Display nested records without assuming a specific resource schema. */
export function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}
