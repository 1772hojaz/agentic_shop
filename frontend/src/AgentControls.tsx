import { useEffect, useState } from 'react';
import { api, type Row } from './api';
import { Form, type Field } from './components';
import type { Perform } from './Resources';

/** Configure the actual agent model and bounded resource controls. */
export function AgentControls({
  perform,
  revision,
}: {
  perform: Perform;
  revision: number;
}) {
  const [config, setConfig] = useState<Row>();
  const [error, setError] = useState('');
  useEffect(() => {
    api<Row>('/ai/config')
      .then(setConfig)
      .catch((failure) => setError(failure.message));
  }, [revision]);
  const fields: Field[] = config
    ? Object.entries(config).map(([name, value]) => ({
        name,
        label: name.replaceAll('_', ' '),
        initial: String(value),
        type: name === 'model' ? 'text' : 'number',
        hint: name.endsWith('price')
          ? 'Provider price per one million tokens; zero disables cost estimation.'
          : undefined,
      }))
    : [];
  return (
    <section className="panel padded">
      <h2>AI model & usage controls</h2>
      <p className="muted">
        API endpoint and credentials stay in the server environment. Changes
        below require confirmation.
      </p>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {config && (
        <Form
          key={revision}
          fields={fields}
          submit={async (values) => {
            const payload = Object.fromEntries(
              Object.entries(values).map(([name, value]) => [
                name,
                name === 'model' ? value : Number(value),
              ]),
            );
            await perform('/ai/config', 'PUT', payload);
          }}
        />
      )}
    </section>
  );
}
