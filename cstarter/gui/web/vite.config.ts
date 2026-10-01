import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// L'interface est servie par pywebview depuis dist/ : des chemins relatifs, aucun serveur externe.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 2000
  }
});
