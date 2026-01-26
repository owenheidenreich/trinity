// Vercel Node.js Function - Dual-protocol proxy to Akash backend
// Supports both HTTP and HTTPS backends with auto-detection
// Handles SSL certificate issues by skipping cert verification for HTTPS

import https from 'https';
import http from 'http';
import { URL } from 'url';

// Akash backend URL from environment variable
// Set via: vercel env add AKASH_URL production
// Supports both http:// and https:// schemes
const AKASH_BASE = process.env.AKASH_URL || 'https://9ibpulolihb210hu1uraei5q8o.ingress.a100.dsm.val.akash.pub';

// Auto-detect protocol from URL
const isHttps = AKASH_BASE.startsWith('https://');

function setCorsHeaders(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');
}

function makeRequest(url, options, body) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const protocol = parsed.protocol === 'https:' ? https : http;
    const defaultPort = parsed.protocol === 'https:' ? 443 : 80;
    
    const requestOptions = {
      hostname: parsed.hostname,
      port: parsed.port || defaultPort,
      path: parsed.pathname + parsed.search,
      method: options.method || 'GET',
      headers: options.headers || {},
    };
    
    // Only add rejectUnauthorized for HTTPS requests
    if (parsed.protocol === 'https:') {
      requestOptions.rejectUnauthorized = false; // Skip SSL verification
    }
    
    const req = protocol.request(requestOptions, (response) => {
      let data = '';
      response.on('data', chunk => data += chunk);
      response.on('end', () => resolve({
        status: response.statusCode,
        headers: response.headers,
        body: data
      }));
    });
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

export default async function handler(req, res) {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    setCorsHeaders(res);
    res.status(204).end();
    return;
  }

  try {
    // Get the original path from the URL (rewrites send original path in req.url)
    // Remove /api/proxy if present, otherwise use the full path
    let path = req.url;
    if (path.startsWith('/api/proxy')) {
      path = path.slice('/api/proxy'.length) || '/';
    }
    const targetUrl = `${AKASH_BASE}${path}`;
    
    console.log(`Proxying: ${req.method} ${path} -> ${targetUrl}`);

    // Collect request body
    let body = null;
    if (req.method !== 'GET' && req.method !== 'HEAD' && req.body) {
      body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
    }

    // Forward headers (filter out problematic ones)
    const forwardHeaders = {};
    for (const [key, value] of Object.entries(req.headers)) {
      if (!['host', 'connection', 'content-length', 'transfer-encoding'].includes(key.toLowerCase())) {
        forwardHeaders[key] = value;
      }
    }
    if (body) {
      forwardHeaders['content-length'] = Buffer.byteLength(body);
    }

    const response = await makeRequest(targetUrl, {
      method: req.method,
      headers: forwardHeaders,
    }, body);

    setCorsHeaders(res);
    res.setHeader('Content-Type', response.headers['content-type'] || 'application/json');
    res.status(response.status).send(response.body);
  } catch (error) {
    setCorsHeaders(res);
    res.status(502).json({
      error: 'Proxy error',
      message: error.message
    });
  }
}
