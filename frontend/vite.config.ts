import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const apiTarget = process.env.SHOP_API_PROXY || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': apiTarget,
      '/uploads': apiTarget,
      '/docs': apiTarget,
      '/openapi.json': apiTarget,
    },
  },
  build: {
    rollupOptions: { output: { manualChunks: { charts: ['recharts'] } } },
  },
});
