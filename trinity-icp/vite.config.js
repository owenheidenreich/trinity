import { defineConfig } from 'vite';
import legacy from '@vitejs/plugin-legacy';
import { resolve } from 'path';

export default defineConfig({
  base: './',
  root: 'src',
  publicDir: false, // Disable public directory since we copy icp-auth.js manually
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    assetsInlineLimit: 0, // Don't inline assets, generate separate files
    rollupOptions: {
      output: {
        format: 'iife', // Use IIFE format for file:// protocol compatibility
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]'
      },
      input: {
        main: resolve(__dirname, 'src/index.html')
      }
    },
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: false, // Keep console.log for now during Phase 4
        drop_debugger: true
      }
    },
    sourcemap: true // Enable source maps for debugging
  },
  plugins: [
    // Disable legacy plugin to avoid module scripts
    // legacy({
    //   targets: ['defaults', 'not IE 11']
    // })
  ],
  server: {
    port: 5173,
    open: true,
    cors: true,
    hmr: {
      overlay: true
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  // Environment variable exposure for Lighthouse integration
  // Note: Primary Lighthouse operations happen on backend for security
  // This is only needed if frontend makes direct Lighthouse SDK calls
  define: {
    'import.meta.env.VITE_LIGHTHOUSE_API_KEY': JSON.stringify(process.env.LIGHTHOUSE_API_KEY || '')
  }
});
