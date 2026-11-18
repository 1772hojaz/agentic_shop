import { display, type Row } from './api';
import type { Field } from './components';
import type { Perform } from './Resources';
import { ROLE_OPTIONS } from './resource-config';

/** Define creation forms and exact API payloads for supported resources. */
export function creation(
  name: string,
  perform: Perform,
):
  | {
      fields: Field[];
      save: (values: Record<string, string>) => Promise<Row>;
    }
  | undefined {
  if (name === 'Products')
    return {
      fields: [
        { name: 'name', label: 'Product name', required: true },
        { name: 'description', label: 'Description', type: 'textarea' },
        { name: 'category_id', label: 'Category ID (optional)' },
        {
          name: 'image_url',
          label: 'Image URL',
          hint: 'Upload an image below, then paste its local URL here, or use HTTPS.',
        },
        { name: 'sku', label: 'SKU', required: true },
        { name: 'price', label: 'Unit price', type: 'number', required: true },
        {
          name: 'quantity',
          label: 'Opening stock',
          type: 'number',
          initial: '0',
        },
        {
          name: 'options',
          label: 'Variant options',
          initial: '{}',
          hint: 'JSON, for example {"size":"42","colour":"black"}',
        },
      ],
      save: (values: Record<string, string>) =>
        perform('/products', 'POST', {
          name: values.name,
          description: values.description,
          category_id: values.category_id || null,
          image_url: values.image_url,
          variants: [
            {
              sku: values.sku,
              price: values.price,
              quantity: Number(values.quantity),
              options: JSON.parse(values.options || '{}'),
            },
          ],
        }),
    };
  if (name === 'Categories')
    return {
      fields: [{ name: 'name', label: 'Category name', required: true }],
      save: (values: Record<string, string>) =>
        perform('/categories', 'POST', values),
    };
  if (name === 'Staff')
    return {
      fields: [
        { name: 'name', label: 'Full name', required: true },
        { name: 'email', label: 'Email', type: 'email', required: true },
        {
          name: 'password',
          label: 'Initial password',
          type: 'password',
          required: true,
          hint: 'At least 12 characters. Share securely.',
        },
        {
          name: 'role',
          label: 'Role',
          options: ROLE_OPTIONS,
          initial: 'staff',
        },
      ],
      save: (values: Record<string, string>) =>
        perform('/staff', 'POST', values),
    };
  if (name === 'Notifications')
    return {
      fields: [
        {
          name: 'kind',
          label: 'Message type',
          options: [
            'text',
            'image',
            'document',
            'interactive',
            'template',
          ].map((value) => ({ value, label: value })),
        },
        { name: 'media_url', label: 'HTTPS media URL (image or document)' },
        {
          name: 'template_name',
          label: 'Approved template name (template only)',
        },
        { name: 'language', label: 'Template language', initial: 'en_US' },
        { name: 'customer_id', label: 'Customer ID', required: true },
        { name: 'text', label: 'Message', type: 'textarea', required: true },
      ],
      save: (values: Record<string, string>) =>
        perform('/notifications', 'POST', values),
    };
}

/** Export visible business records while neutralizing spreadsheet formulas. */
export function exportCsv(name: string, rows: Row[]): void {
  const columns = Object.keys(rows[0]);
  const escape = (value: unknown) => {
    let text = display(value);
    if (/^[=+@\-\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const csv = [
    columns.map(escape).join(','),
    ...rows.map((row) => columns.map((key) => escape(row[key])).join(',')),
  ].join('\r\n');
  const url = URL.createObjectURL(
    new Blob([csv], { type: 'text/csv;charset=utf-8' }),
  );
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name.toLowerCase().replaceAll(' ', '-') + '.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}
