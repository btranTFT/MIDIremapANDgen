import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    strictPort: true,
    host: true,
    proxy: {
      '/api': 'http://localhost:8001',
      '/download': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
    },
  },
});

