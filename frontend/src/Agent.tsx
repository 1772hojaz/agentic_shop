import { useEffect, useState } from 'react';
import { Bot, Send, ShieldCheck } from 'lucide-react';
import { api, type Page, type Pending, type Row } from './api';
import { DataTable, Details } from './components';
import type { Perform } from './Resources';

/** Provide a real administrator agent conversation and measured usage. */
export function Agent({
  perform,
  revision,
}: {
  perform: Perform;
  revision: number;
}) {
  const [message, setMessage] = useState('');
  const [conversation, setConversation] = useState<string>();
  const [turns, setTurns] = useState<{ role: string; text: string }[]>([]);
  const [usage, setUsage] = useState<Page & Row>();
  const [pending, setPending] = useState<Pending[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api<Page & Row>('/ai/usage')
      .then((result) => {
        if (active) setUsage(result);
      })
      .catch(() => {});
    api<Page>('/confirmations')
      .then((result) => {
        if (active) setPending(result.items as unknown as Pending[]);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [revision, turns]);
  async function send() {
    if (!message.trim() || busy) return;
    const text = message;
    setBusy(true);
    setError('');
    try {
      const result = await api<{
        conversation_id: string;
        message: string;
        confirmations: Pending[];
      }>('/ai/chat', 'POST', {
        message: text,
        conversation_id: conversation || null,
      });
      setConversation(result.conversation_id);
      setTurns((previous) => [
        ...previous,
        { role: 'You', text },
        { role: 'Shop assistant', text: result.message },
      ]);
      setMessage('');
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ONE AGENT. CONTROLLED ACCESS.</div>
          <h1>Your shop assistant</h1>
          <p>Ask questions. Request actions. Stay in control.</p>
        </div>
        <span className="badge paid">
          <ShieldCheck size={14} />
          Administrator context
        </span>
      </div>
      <div className="agent-grid">
        <section className="panel chat-panel">
          <div className="panel-heading">
            <div className="inline-heading">
              <Bot size={22} />
              <div>
                <h2>Agent workspace</h2>
                <p>Connected to your permission-aware tools</p>
              </div>
            </div>
          </div>
          <div className="chat-log" aria-live="polite">
            {!turns.length && (
              <div className="empty">
                <Bot size={36} />
                <h3>A little help for your everyday work</h3>
                <p>
                  Try “Which products are running low?” or “Show this month’s
                  sales.”
                </p>
                <small>
                  An external model must be configured on the server.
                </small>
              </div>
            )}
            {turns.map((turn, index) => (
              <div
                className={`chat-turn ${turn.role === 'You' ? 'human' : ''}`}
                key={index}
              >
                <strong>{turn.role}</strong>
                <p>{turn.text}</p>
              </div>
            ))}
            {busy && <p className="muted">Working with your shop tools…</p>}
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <form
            className="chat-input"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <input
              aria-label="Message to shop assistant"
              maxLength={4000}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Ask your shop assistant…"
            />
            <button
              className="primary"
              disabled={busy || !message.trim()}
              aria-label="Send message"
            >
              <Send size={18} />
            </button>
          </form>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Awaiting your approval</h2>
              <p>Review the exact action before confirming.</p>
            </div>
          </div>
          {pending.length ? (
            pending.map((item) => (
              <div className="pending" key={item.id}>
                <strong>{item.action.replaceAll('_', ' ')}</strong>
                <Details row={item.payload} />
                <button
                  className="secondary"
                  onClick={() =>
                    void perform(
                      `/confirmations/${item.id}/confirm`,
                      'POST',
                    ).catch((failure) => setError(failure.message))
                  }
                >
                  Approve this action
                </button>
              </div>
            ))
          ) : (
            <div className="empty">
              <ShieldCheck size={28} />
              <p>No actions awaiting confirmation.</p>
            </div>
          )}
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Model usage</h2>
            <p>
              {Number(usage?.input_tokens || 0).toLocaleString()} input tokens
              · {Number(usage?.output_tokens || 0).toLocaleString()} output
              tokens · ${Number(usage?.estimated_cost || 0).toFixed(4)}{' '}
              estimated spend
            </p>
          </div>
        </div>
        <DataTable
          rows={usage?.items || []}
          columns={[
            ['model', 'Model'],
            ['input_tokens', 'Input tokens'],
            ['output_tokens', 'Output tokens'],
            ['estimated_cost', 'Estimated cost'],
            ['created_at', 'Time'],
          ]}
        />
      </section>
    </>
  );
}
