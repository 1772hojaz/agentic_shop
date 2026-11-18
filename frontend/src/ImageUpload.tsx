import { useState } from 'react';
import { api } from './api';

/** Upload a validated product image and provide its local catalogue URL. */
export function ImageUpload() {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError('');
    const body = new FormData();
    body.append('file', file);
    try {
      const result = await api<{ url: string }>('/uploads', 'POST', body);
      setUrl(result.url);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel padded pairing">
      <h2>Product images</h2>
      <p className="muted">Upload a PNG, JPEG, or WebP under 5 MB.</p>
      <input
        aria-label="Upload product image"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        disabled={busy}
        onChange={(event) => void upload(event.target.files?.[0])}
      />
      {busy && <p>Uploading…</p>}
      {url && (
        <>
          <img className="upload-preview" src={url} alt="Uploaded product" />
          <label>
            Image URL
            <input
              readOnly
              value={url}
              onFocus={(event) => event.target.select()}
            />
          </label>
        </>
      )}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}
