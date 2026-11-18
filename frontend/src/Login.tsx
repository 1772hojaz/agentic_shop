import { Bot, MessageCircle, ShieldCheck, ShoppingBag } from 'lucide-react';
import { api, setCsrf, type Identity } from './api';
import { Form } from './components';

/** Authenticate against the server without demo accounts or local tokens. */
export function Login({ accept }: { accept: (identity: Identity) => void }) {
  return (
    <div className="login-page">
      <div className="login-story">
        <a className="brand" href="#">
          <span className="brand-mark">
            <ShoppingBag size={24} />
          </span>
          <div>
            agentic<span>YOUR SHOP, CONNECTED</span>
          </div>
        </a>
        <div>
          <span className="eyebrow">
            A LITTLE INTELLIGENCE. A LOT OF POSSIBILITIES.
          </span>
          <h1>
            A smoother day
            <br />
            for your shop.
          </h1>
          <p>
            Your products, people, and conversations.
            <br />
            Together in one thoughtful workspace.
          </p>
          <div className="login-illustration">
            <div>
              <MessageCircle size={30} />
              <span>Conversations</span>
            </div>
            <i />
            <div className="illustration-agent">
              <Bot size={36} />
              <span>One assistant</span>
            </div>
            <i />
            <div>
              <ShoppingBag size={30} />
              <span>Your business</span>
            </div>
          </div>
        </div>
        <small>Built for better business, one conversation at a time.</small>
      </div>
      <section className="login-form">
        <div>
          <span className="eyebrow">WELCOME BACK</span>
          <h2>Let’s get to work.</h2>
          <p className="muted">Sign in to your shop administration account.</p>
          <Form
            label="Sign in to workspace"
            fields={[
              {
                name: 'email',
                label: 'Email address',
                type: 'email',
                required: true,
              },
              {
                name: 'password',
                label: 'Password',
                type: 'password',
                required: true,
              },
            ]}
            submit={async (values) => {
              const result = await api<{ csrf_token: string }>(
                '/auth/login',
                'POST',
                values,
              );
              setCsrf(result.csrf_token);
              accept(await api<Identity>('/auth/me'));
            }}
          />
          <div className="login-note">
            <ShieldCheck size={17} />
            <span>
              Secure access for authorised shop staff.
              <br />
              Contact your shop owner for an account.
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
