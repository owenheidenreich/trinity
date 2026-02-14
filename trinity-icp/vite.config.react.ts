import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  base: './',
  root: 'src-react',
  publicDir: 'public',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    assetsInlineLimit: 0,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'src-react/index.html'),
      },
    },
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_debugger: true,
      },
    },
    sourcemap: true,
  },
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    cors: true,
    hmr: {
      overlay: true,
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src-react'),
    },
  },
  css: {
    modules: {
      localsConvention: 'camelCaseOnly',
    },
  },
  define: {
    'import.meta.env.VITE_LIGHTHOUSE_API_KEY': JSON.stringify(
      process.env.LIGHTHOUSE_API_KEY || ''
    ),
  },
});
