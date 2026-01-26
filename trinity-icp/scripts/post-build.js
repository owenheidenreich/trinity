// Post-build script to make dist compatible with file:// protocol
import { readFileSync, writeFileSync, readdirSync, copyFileSync, mkdirSync, existsSync } from 'fs';
import { resolve, dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const indexPath = resolve(__dirname, '../dist/index.html');
const assetsDir = resolve(__dirname, '../dist/assets');
const distDir = resolve(__dirname, '../dist');
const srcDir = resolve(__dirname, '../src');

console.log('📝 Post-processing index.html for file:// protocol support...');

let html = readFileSync(indexPath, 'utf-8');

// Find the main bundle file
const files = readdirSync(assetsDir);
const mainBundle = files.find(f => f.startsWith('main-') && f.endsWith('.js'));

if (!mainBundle) {
  console.error('❌ Could not find main bundle in assets/');
  process.exit(1);
}

console.log(`✅ Found main bundle: ${mainBundle}`);

// Remove type="module" attribute but keep the script tags
html = html.replace(/(<script[^>]*)\s+type="module"([^>]*>)/g, '$1$2');
html = html.replace(/\s+crossorigin/g, '');

// Add icp-auth.js script BEFORE the main bundle
const icpAuthScript = '\n    <!-- ICP Authentication Bundle (must load before main) -->\n    <script src="icp-auth.js?v=3"></script>';
// Add main bundle script
const mainBundleScript = `\n    <!-- Main App Bundle -->\n    <script src="./assets/${mainBundle}"></script>`;

html = html.replace('</body>', icpAuthScript + mainBundleScript + '\n</body>');

writeFileSync(indexPath, html, 'utf-8');

console.log('✅ index.html processed - file:// protocol should now work');

// Copy icp-auth.js to dist
const icpAuthSource = resolve(__dirname, '../src/auth/icp-auth.js');
const icpAuthDest = join(distDir, 'icp-auth.js');
copyFileSync(icpAuthSource, icpAuthDest);
console.log('✅ icp-auth.js copied to dist/');

// Copy styles.css to dist
const stylesSource = resolve(__dirname, '../src/styles.css');
const stylesDest = join(distDir, 'styles.css');
copyFileSync(stylesSource, stylesDest);
console.log('✅ styles.css copied to dist/');

// Add styles.css link to HTML if not present
if (!html.includes('styles.css')) {
    html = html.replace('</head>', '    <link rel="stylesheet" href="styles.css">\n</head>');
    writeFileSync(indexPath, html, 'utf-8');
    console.log('✅ styles.css link added to index.html');
}

// Add global function wrappers AFTER the IIFE to expose them to onclick handlers
const mainBundlePath = join(assetsDir, mainBundle);
let jsContent = readFileSync(mainBundlePath, 'utf-8');

const hasWindowAssignments = jsContent.includes('window.Actions=');
console.log(`📊 Bundle has window.Actions assignment: ${hasWindowAssignments}`);

if (!hasWindowAssignments) {
  console.warn('⚠️ No window.Actions found in bundle - functions may not work!');
  console.log('💡 This might be a Vite IIFE bundling issue');
}

// No need to append wrappers - the IIFE already assigns window functions
console.log('✅ Using IIFE-assigned window functions (no wrapper needed)');

writeFileSync(mainBundlePath, jsContent, 'utf-8');

// Copy .well-known folder for ICP custom domain registration
const wellKnownSrc = join(srcDir, '.well-known');
const wellKnownDest = join(distDir, '.well-known');
if (existsSync(wellKnownSrc)) {
    if (!existsSync(wellKnownDest)) {
        mkdirSync(wellKnownDest, { recursive: true });
    }
    const wellKnownFiles = readdirSync(wellKnownSrc);
    for (const file of wellKnownFiles) {
        copyFileSync(join(wellKnownSrc, file), join(wellKnownDest, file));
    }
    console.log('✅ .well-known folder copied to dist/');
}

// Copy .ic-assets.json5 for ICP asset configuration
const icAssetsSource = join(srcDir, '.ic-assets.json5');
const icAssetsDest = join(distDir, '.ic-assets.json5');
if (existsSync(icAssetsSource)) {
    copyFileSync(icAssetsSource, icAssetsDest);
    console.log('✅ .ic-assets.json5 copied to dist/');
}