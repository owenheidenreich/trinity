import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src-react'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src-react/test-setup.ts'],
    include: ['src-react/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src-react/**/*.{ts,tsx}'],
      exclude: ['src-react/**/*.test.*', 'src-react/**/*.spec.*', 'src-react/types/**'],
    },
  },
});
