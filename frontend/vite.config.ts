import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';

export default defineConfig({
  plugins: [react()],
  server: {
    port: parseInt(process.env.VITE_PORT ?? '3000', 10),
    strictPort: true,
    host: true,
    proxy: {
      '/api': process.env.VITE_API_BASE ?? 'http://localhost:8001',
      '/download': process.env.VITE_API_BASE ?? 'http://localhost:8001',
      '/health': process.env.VITE_API_BASE ?? 'http://localhost:8001',
    },
  },
});

