// Build script to bundle @dfinity libraries for browser
const esbuild = require('esbuild');

esbuild.build({
  entryPoints: ['src/auth/auth-entry.js'],
  bundle: true,
  outfile: 'src/auth/icp-auth.js',
  format: 'iife',
  globalName: 'ICPAuth',
  platform: 'browser',
  target: 'es2020',
  minify: false, // Keep readable for debugging
  sourcemap: true,
}).then(() => {
  console.log('✅ ICP Auth bundle created: src/auth/icp-auth.js');
}).catch((error) => {
  console.error('❌ Build failed:', error);
  process.exit(1);
});
