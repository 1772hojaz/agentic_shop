import type { Identity, Row } from './api';
import type { Field } from './components';
import type { Perform } from './Resources';
import { ORDER_STATES, ROLE_OPTIONS } from './resource-config';

interface ActionProps {
  name: string;
  row: Row;
  identity: Identity;
  perform: Perform;
  reload: () => void;
  openForm: (
    title: string,
    fields: Field[],
    save: (values: Record<string, string>) => Promise<unknown>,
  ) => void;
}

/** Render service-specific operations with explicit permissions and forms. */
export function RowActions(props: ActionProps) {
  const { name, row, identity, perform, openForm, reload } = props;
  const can = (permission: string) =>
    identity.permissions.includes(permission);
  const save = async (path: string, method: string, data?: unknown) => {
    await perform(path, method, data);
    reload();
  };
  return (
    <div className="row-actions">
      {name === 'Categories' && can('products.write') && (
        <button
          className="secondary"
          onClick={() =>
            openForm(
              'Rename category',
              [
                {
                  name: 'name',
                  label: 'Category name',
                  required: true,
                  initial: String(row.name),
                },
              ],
              (values) => save(`/categories/${row.id}`, 'PATCH', values),
            )
          }
        >
          Rename category
        </button>
      )}
      {name === 'Products' && can('products.write') && (
        <button
          className="secondary"
          onClick={() =>
            openForm(
              'Add variant',
              [
                { name: 'sku', label: 'Unique SKU', required: true },
                {
                  name: 'price',
                  label: 'Price',
                  type: 'number',
                  required: true,
                },
                {
                  name: 'quantity',
                  label: 'Opening stock',
                  type: 'number',
                  initial: '0',
                },
                {
                  name: 'options',
                  label: 'Variant options as JSON',
                  initial: '{}',
                },
              ],
              (values) =>
                save(`/products/${row.id}/variants`, 'POST', {
                  ...values,
                  quantity: Number(values.quantity),
                  options: JSON.parse(values.options),
                }),
            )
          }
        >
          Add variant
        </button>
      )}
      {name === 'Inventory' && can('inventory.write') && (
        <button
          className="secondary"
          onClick={() =>
            openForm(
              'Low-stock alert threshold',
              [
                {
                  name: 'threshold',
                  label: 'Notify when available units reach',
                  type: 'number',
                  initial: String(row.low_stock_threshold),
                },
              ],
              (values) =>
                save(`/inventory/${row.variant_id}/threshold`, 'PATCH', {
                  variant_id: row.variant_id,
                  threshold: Number(values.threshold),
                }),
            )
          }
        >
          Set alert threshold
        </button>
      )}
      {name === 'Products' && can('products.write') && (
        <>
          <button
            className="secondary"
            onClick={() =>
              openForm(
                'Edit product',
                ['name', 'description', 'category_id', 'image_url'].map(
                  (key) => ({
                    name: key,
                    label: key.replaceAll('_', ' '),
                    initial: row[key] ? String(row[key]) : '',
                  }),
                ),
                (values) =>
                  save(`/products/${row.id}`, 'PATCH', {
                    ...values,
                    category_id: values.category_id || null,
                    active: true,
                  }),
              )
            }
          >
            Edit product
          </button>
          <button
            className="secondary"
            onClick={() =>
              openForm(
                'Change variant price',
                [
                  {
                    name: 'variant_id',
                    label: 'Variant ID',
                    required: true,
                    initial: String((row.variants as Row[])?.[0]?.id || ''),
                  },
                  {
                    name: 'price',
                    label: 'New price',
                    type: 'number',
                    required: true,
                  },
                ],
                (values) =>
                  save(`/variants/${values.variant_id}/price`, 'POST', values),
              )
            }
          >
            Change price
          </button>
          <button
            className="danger"
            onClick={() =>
              openForm(
                'Archive product',
                [
                  {
                    name: 'confirm',
                    label: 'Type ARCHIVE to hide this product',
                    required: true,
                  },
                ],
                async (values) => {
                  if (values.confirm !== 'ARCHIVE')
                    throw new Error('Type ARCHIVE to proceed.');
                  return save(`/products/${row.id}`, 'DELETE');
                },
              )
            }
          >
            Archive
          </button>
        </>
      )}
      {name === 'Inventory' && can('inventory.write') && (
        <button
          className="primary"
          onClick={() =>
            openForm(
              'Adjust stock',
              [
                {
                  name: 'delta',
                  label: 'Quantity change',
                  type: 'number',
                  required: true,
                  hint: 'Positive adds units; negative removes units.',
                },
                { name: 'reason', label: 'Reason', required: true },
              ],
              (values) =>
                save(`/inventory/${row.variant_id}`, 'PATCH', {
                  variant_id: row.variant_id,
                  delta: Number(values.delta),
                  reason: values.reason,
                }),
            )
          }
        >
          Adjust stock
        </button>
      )}
      {name === 'Orders' && can('orders.write') && (
        <button
          className="primary"
          onClick={() =>
            openForm(
              'Update order',
              [
                {
                  name: 'status',
                  label: 'New status',
                  options: ORDER_STATES.filter(
                    (state) =>
                      ![
                        'pending_payment',
                        'paid',
                        'expired',
                        'refunded',
                      ].includes(state),
                  ).map((value) => ({
                    value,
                    label: value.replaceAll('_', ' '),
                  })),
                },
                { name: 'tracking', label: 'Delivery information' },
              ],
              (values) =>
                save(`/orders/${row.id}/status`, 'PATCH', {
                  ...values,
                  order_id: row.id,
                }),
            )
          }
        >
          Update status
        </button>
      )}
      {name === 'Orders' && can('payments.write') && (
        <button
          className="secondary"
          onClick={() =>
            openForm(
              'Payment operation',
              [
                {
                  name: 'id',
                  label: 'Payment ID from the order details',
                  required: true,
                },
                {
                  name: 'action',
                  label: 'Operation',
                  options: [
                    { value: 'settle-cash', label: 'Record cash received' },
                    { value: 'refund', label: 'Refund Stripe payment' },
                  ],
                },
              ],
              (values) =>
                save(`/payments/${values.id}/${values.action}`, 'POST'),
            )
          }
        >
          Manage payment
        </button>
      )}
      {name === 'Staff' && can('staff.write') && (
        <button
          className="secondary"
          onClick={() =>
            openForm(
              'Staff access',
              [
                {
                  name: 'role',
                  label: 'Role',
                  options: ROLE_OPTIONS,
                  initial: String((row.roles as string[])?.[0] || 'staff'),
                },
                {
                  name: 'active',
                  label: 'Account status',
                  initial: String(row.active),
                  options: [
                    { value: 'true', label: 'Active' },
                    { value: 'false', label: 'Disabled' },
                  ],
                },
              ],
              (values) =>
                save(`/staff/${row.id}`, 'PATCH', {
                  role: values.role,
                  active: values.active === 'true',
                }),
            )
          }
        >
          Edit access
        </button>
      )}
      {name === 'Roles and Permissions' &&
        row.name !== 'owner' &&
        can('staff.write') && (
          <button
            className="secondary"
            onClick={() =>
              openForm(
                'Role permissions',
                [
                  {
                    name: 'permissions',
                    label: 'Permissions (comma separated)',
                    type: 'textarea',
                    initial: (row.permissions as string[]).join(', '),
                  },
                ],
                (values) =>
                  save(`/roles/${row.id}`, 'PATCH', {
                    permissions: values.permissions
                      .split(',')
                      .map((value) => value.trim())
                      .filter(Boolean),
                  }),
              )
            }
          >
            Edit permissions
          </button>
        )}
    </div>
  );
}
