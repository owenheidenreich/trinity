// Vercel Node.js Function - Dual-protocol proxy to Akash backend
// Supports both HTTP and HTTPS backends with auto-detection
// Handles SSL certificate issues by skipping cert verification for HTTPS
// Supports SSE streaming for /generate/stream endpoint

import https from 'https';
import http from 'http';
import { URL } from 'url';

// Akash backend URL from environment variable
// Set via: vercel env add AKASH_URL production
// Supports both http:// and https:// schemes
const AKASH_BASE = process.env.AKASH_URL || 'https://6i2rtl1m35a47bb0n47jr7c17c.ingress.a100.dsm.val.akash.pub';

// Auto-detect protocol from URL
const isHttps = AKASH_BASE.startsWith('https://');

function setCorsHeaders(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');
}

// Streaming request handler - pipes chunks directly to client
function makeStreamingRequest(url, options, body, res) {
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
      requestOptions.rejectUnauthorized = false;
    }
    
    const req = protocol.request(requestOptions, (response) => {
      // Set SSE headers on client response
      setCorsHeaders(res);
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
      }, body, res);
      return;
    }

    // Standard request/response for non-streaming
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
