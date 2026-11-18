import { useEffect, useState } from 'react';
import { api, type Row } from './api';
import { Form, type Field } from './components';
import type { Perform } from './Resources';
import { ImageUpload } from './ImageUpload';
import { AgentControls } from './AgentControls';

/** Edit non-secret settings and inspect actual provider configuration. */
export function Settings({
  perform,
  revision,
}: {
  perform: Perform;
  revision: number;
}) {
  const [settings, setSettings] = useState<Row>();
  const [error, setError] = useState('');
  const [pairing, setPairing] = useState('');
  useEffect(() => {
    api<Row>('/settings')
      .then(setSettings)
      .catch((failure) => setError(failure.message));
  }, [revision]);
  if (error)
    return (
      <div className="error" role="alert">
        {error}
      </div>
    );
  if (!settings) return <div className="loading">Loading settings…</div>;
  const shop = settings.shop as Row;
  const fields: Field[] = [
    'name',
    'contact',
    'delivery_instructions',
    'support_message',
    'agent_instructions',
  ].map((name) => ({
    name,
    label: name.replaceAll('_', ' '),
    type:
      name.endsWith('instructions') || name.endsWith('message')
        ? 'textarea'
        : 'text',
    initial: String(shop[name] || ''),
  }));
  fields.push({
    name: 'notifications_enabled',
    label: 'Order notifications',
    initial: String(shop.notifications_enabled ?? true),
    options: [
      { value: 'true', label: 'Enabled' },
      { value: 'false', label: 'Disabled' },
    ],
  });
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">MAKE IT YOUR SHOP</div>
          <h1>Settings & integrations</h1>
          <p>Business preferences, safe connections, and account pairing.</p>
        </div>
      </div>
      <div className="settings-grid">
        <section className="panel padded">
          <h2>Shop preferences</h2>
          <p className="muted">Changes require your explicit confirmation.</p>
          <Form
            key={revision}
            fields={fields}
            submit={async (values) => {
              await perform('/settings', 'PUT', {
                ...values,
                notifications_enabled: values.notifications_enabled === 'true',
              });
            }}
          />
        </section>
        <div>
          <section className="panel padded">
            <h2>Connected services</h2>
            <p className="muted">
              Credentials are managed securely on the server.
            </p>
            {Object.entries(settings.integrations as Row).map(
              ([key, value]) => (
                <div className="operation-row" key={key}>
                  <strong>
                    {key === 'ai'
                      ? 'External AI model'
                      : key === 'stripe'
                        ? 'Stripe payments'
                        : 'WhatsApp Cloud API'}
                  </strong>
                  <span
                    className={`badge ${value ? 'paid' : 'pending_payment'}`}
                  >
                    {value ? 'Configured' : 'Not configured'}
                  </span>
                </div>
              ),
            )}
            <p className="muted">
              Currency: {String(settings.currency)}
              <br />
              Model: {String(settings.model || 'Not configured')}
              <br />
              Daily token limit: {String(settings.daily_tokens)}
            </p>
          </section>
          <section className="panel padded pairing">
            <h2>Manage through WhatsApp</h2>
            <p className="muted">
              Pair from this authenticated account. The code expires in five
              minutes; access lasts one hour.
            </p>
            <button
              className="secondary"
              onClick={() =>
                api<{ instruction: string }>('/auth/whatsapp-pairing', 'POST')
                  .then((result) => setPairing(result.instruction))
                  .catch((failure) => setError(failure.message))
              }
            >
              Generate pairing code
            </button>
            {pairing && <p className="pairing-code">{pairing}</p>}
          </section>
          <AgentControls perform={perform} revision={revision} />
          <ImageUpload />
        </div>
      </div>
    </>
  );
}
