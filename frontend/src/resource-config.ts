interface Config {
  path: string;
  description: string;
  columns: [string, string][];
  permission?: string;
}
export const CONFIG: Record<string, Config> = {
  Products: {
    path: '/products',
    description: 'A thoughtful catalogue, ready for your customers.',
    permission: 'products.write',
    columns: [
      ['name', 'Product'],
      ['description', 'Description'],
      ['active', 'Available'],
    ],
  },
  Categories: {
    path: '/categories',
    description: 'Bring a little structure to your catalogue.',
    permission: 'products.write',
    columns: [
      ['name', 'Category'],
      ['created_at', 'Created'],
    ],
  },
  Inventory: {
    path: '/inventory',
    description: 'Know what is in stock, and what needs attention.',
    permission: 'inventory.write',
    columns: [
      ['name', 'Product'],
      ['sku', 'SKU'],
      ['quantity', 'Available'],
      ['low_stock_threshold', 'Low-stock threshold'],
    ],
  },
  Orders: {
    path: '/orders',
    description: 'Every order, from first checkout to final delivery.',
    permission: 'orders.write',
    columns: [
      ['id', 'Order reference'],
      ['created_at', 'Placed'],
      ['total', 'Total'],
      ['status', 'Status'],
    ],
  },
  Customers: {
    path: '/customers',
    description: 'The people at the heart of your business.',
    columns: [
      ['name', 'Customer'],
      ['phone', 'WhatsApp number'],
      ['created_at', 'First seen'],
    ],
  },
  'WhatsApp Conversations': {
    path: '/conversations',
    description: 'Follow the conversations happening across your shop.',
    columns: [
      ['id', 'Conversation'],
      ['channel', 'Channel'],
      ['context', 'Context'],
      ['created_at', 'Started'],
    ],
  },
  Notifications: {
    path: '/notifications',
    description: 'Customer updates and their delivery progress.',
    permission: 'notifications.write',
    columns: [
      ['recipient', 'Recipient'],
      ['status', 'Delivery'],
      ['attempts', 'Attempts'],
      ['error', 'Last error'],
    ],
  },
  Staff: {
    path: '/staff',
    description: 'Give your team the right access to do great work.',
    permission: 'staff.write',
    columns: [
      ['name', 'Name'],
      ['email', 'Email'],
      ['roles', 'Roles'],
      ['active', 'Active'],
    ],
  },
  'Roles and Permissions': {
    path: '/roles',
    description: 'Clear responsibilities. Controlled access.',
    permission: 'staff.write',
    columns: [
      ['name', 'Role'],
      ['permissions', 'Permissions'],
    ],
  },
  'Audit Log': {
    path: '/audit',
    description: 'A clear record of important business operations.',
    columns: [
      ['action', 'Action'],
      ['actor_id', 'Actor'],
      ['entity_id', 'Record'],
      ['created_at', 'Time'],
    ],
  },
  'Stock Movements': {
    path: '/inventory/movements',
    description: 'The reason behind every inventory change.',
    columns: [
      ['variant_id', 'Variant'],
      ['delta', 'Change'],
      ['reason', 'Reason'],
      ['created_at', 'Time'],
    ],
  },
};

export const ROLE_OPTIONS = ['owner', 'manager', 'staff'].map((value) => ({
  value,
  label: value,
}));
export const ORDER_STATES = [
  'pending_payment',
  'paid',
  'processing',
  'ready_for_delivery',
  'out_for_delivery',
  'delivered',
  'completed',
  'cancelled',
  'expired',
  'delivery_failed',
  'refund_pending',
  'refunded',
];
