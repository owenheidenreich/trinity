// Vercel Node.js Function - Dual-protocol proxy to Akash backend
// Supports both HTTP and HTTPS backends with auto-detection
// Handles SSL certificate issues by skipping cert verification for HTTPS
// Supports SSE streaming for /generate/stream endpoint

import https from 'https';
import http from 'http';
import { URL } from 'url';

// Akash backend URL from environment variable
// Set via: vercel env add AKASH_URL production
// SECURITY: Remove hardcoded fallback URL in production
const AKASH_BASE = process.env.AKASH_URL;
if (!AKASH_BASE) {
  console.error('CRITICAL: AKASH_URL environment variable is not set');
}

// Auto-detect protocol from URL
const isHttps = AKASH_BASE?.startsWith('https://') ?? true;

// Allowed origins for CORS - restrict to known frontends
const ALLOWED_ORIGINS = [
  'https://trinityai.cc',
  'https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io',
  'https://zc67k-kiaaa-aaaal-qtmiq-cai.raw.icp0.io',
  'http://localhost:5173', // Development
  'http://localhost:3000', // Development
  'http://127.0.0.1:5173',
];

function setCorsHeaders(res, origin) {
  // Check if origin is allowed
  const allowedOrigin = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  res.setHeader('Access-Control-Allow-Origin', allowedOrigin);
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Accept, ICP-Principal, ICP-Timestamp, ICP-Signature, ICP-PublicKey, X-Trinity-Session, X-Request-ID');
  res.setHeader('Access-Control-Allow-Credentials', 'true');

  // Security headers
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('X-XSS-Protection', '1; mode=block');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
}

// Streaming request handler - pipes chunks directly to client
function makeStreamingRequest(url, options, body, res, origin) {
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
    
    if (parsed.protocol === 'https:') {
      // SECURITY NOTE: SSL verification is disabled because Akash providers
      // use self-signed certificates. This is an intentional trade-off.
      // TODO: Implement certificate pinning for trusted Akash providers
      requestOptions.rejectUnauthorized = false;
    }
    
    const req = protocol.request(requestOptions, (response) => {
      // Set SSE headers on client response
      setCorsHeaders(res, origin);
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
      res.setHeader('X-Accel-Buffering', 'no');
      res.status(response.statusCode);
      
      // Pipe each chunk directly to client
      response.on('data', chunk => {
        res.write(chunk);
      });
      
      response.on('end', () => {
        res.end();
        resolve();
      });
    });
    
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
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
    
    // SECURITY NOTE: SSL verification is disabled because Akash providers
    // use self-signed certificates. This is an intentional trade-off.
    // TODO: Implement certificate pinning for trusted Akash providers
    if (parsed.protocol === 'https:') {
      requestOptions.rejectUnauthorized = false;
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
  const origin = req.headers.origin || '';

  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    setCorsHeaders(res, origin);
    res.status(204).end();
    return;
  }

  try {
    // Check for private session override via header
    // Frontend sends X-Trinity-Session header with private instance URL
    const sessionUrl = req.headers['x-trinity-session'];
    const baseUrl = sessionUrl || AKASH_BASE;
    
    // Get the original path from the URL (rewrites send original path in req.url)
    // Remove /api/proxy if present, otherwise use the full path
    let path = req.url;
    if (path.startsWith('/api/proxy')) {
      path = path.slice('/api/proxy'.length) || '/';
    }
    const targetUrl = `${baseUrl}${path}`;
    
    // Check if this is a streaming request
    const isStreamingRequest = path.includes('/generate/stream');
    
    console.log(`Proxying: ${req.method} ${path} -> ${targetUrl}${isStreamingRequest ? ' (streaming)' : ''}`);

    // Collect request body
    let body = null;
    if (req.method !== 'GET' && req.method !== 'HEAD' && req.body) {
      body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
    }

    // Forward headers (filter out problematic ones)
    const forwardHeaders = {};
    for (const [key, value] of Object.entries(req.headers)) {
      if (!['host', 'connection', 'content-length', 'transfer-encoding', 'accept-encoding'].includes(key.toLowerCase())) {
        forwardHeaders[key] = value;
      }
    }
    // Explicitly request uncompressed responses - the proxy handles text, not binary
    forwardHeaders['accept-encoding'] = 'identity';
    if (body) {
      forwardHeaders['content-length'] = Buffer.byteLength(body);
    }

    // Use streaming handler for SSE endpoints
    if (isStreamingRequest) {
      await makeStreamingRequest(targetUrl, {
        method: req.method,
        headers: forwardHeaders,
      }, body, res, origin);
      return;
    }

    // Standard request/response for non-streaming
    const response = await makeRequest(targetUrl, {
      method: req.method,
      headers: forwardHeaders,
    }, body);

    setCorsHeaders(res, origin);
    res.setHeader('Content-Type', response.headers['content-type'] || 'application/json');
    res.status(response.status).send(response.body);
  } catch (error) {
    console.error('Proxy error:', error.message);
    setCorsHeaders(res, origin);
    // SECURITY: Don't expose internal error details to clients
    res.status(502).json({
      error: 'Proxy error',
      message: 'Failed to connect to backend service'
    });
  }
}
