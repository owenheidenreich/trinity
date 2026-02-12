/**
 * Trinity Cloudflare Worker Proxy
 * Routes api.dubya.ai/* → Akash Backend
 * 
 * Environment secrets required:
 *   AKASH_URL - The Akash backend URL (set via: wrangler secret put AKASH_URL)
 */

// Allowed origins for CORS
const ALLOWED_ORIGINS = [
  'https://dubya.ai',
  'https://www.dubya.ai',
  'https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io',
  'https://zc67k-kiaaa-aaaal-qtmiq-cai.raw.icp0.io',
  'http://localhost:5173',
  'http://localhost:3000',
  'http://127.0.0.1:5173',
];

function getCorsHeaders(origin) {
  const allowedOrigin = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allowedOrigin,
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept, ICP-Principal, ICP-Timestamp, ICP-Signature, ICP-PublicKey, ICP-Nonce, X-Trinity-Session, X-Request-ID',
    'Access-Control-Allow-Credentials': 'true',
    // Security headers
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Content-Security-Policy':
      "default-src 'self'; " +
      "script-src 'self' https://cdn.jsdelivr.net; " +
      "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; " +
      "connect-src 'self' https://api.dubya.ai; " +
      "img-src 'self' data: https:; " +
      "font-src 'self' https://cdn.jsdelivr.net; " +
      "frame-ancestors 'none';",
  };
}

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get('Origin') || '';
    const corsHeaders = getCorsHeaders(origin);

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: corsHeaders,
      });
    }

    try {
      // Check for AKASH_URL secret
      if (!env.AKASH_URL) {
        console.error('CRITICAL: AKASH_URL secret is not set');
        return new Response(
          JSON.stringify({ 
            error: 'Proxy configuration error', 
            message: 'Backend URL not configured. Run: wrangler secret put AKASH_URL' 
          }),
          { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }

      // Get the path from request URL
      const url = new URL(request.url);
      const path = url.pathname + url.search;
      
      // Build target URL (ensure no double slashes)
      const baseUrl = env.AKASH_URL.replace(/\/$/, '');
      const targetUrl = `${baseUrl}${path}`;

      // Check if this is a streaming request
      const isStreamingRequest = path.includes('/generate/stream') || path.includes('/generate/agent');

      console.log(`Proxying: ${request.method} ${path} -> ${targetUrl}${isStreamingRequest ? ' (streaming)' : ''}`);

      // Build headers to forward
      const forwardHeaders = new Headers();
      for (const [key, value] of request.headers.entries()) {
        const lowerKey = key.toLowerCase();
        // Skip Cloudflare-specific and hop-by-hop headers
        if (!['host', 'connection', 'content-length', 'transfer-encoding', 'accept-encoding', 
              'cf-connecting-ip', 'cf-ray', 'cf-visitor', 'cf-ipcountry', 'cf-request-id',
              'cdn-loop', 'x-forwarded-proto', 'x-forwarded-for'].includes(lowerKey)) {
          forwardHeaders.set(key, value);
        }
      }
      
      // Request uncompressed responses for easier handling
      forwardHeaders.set('Accept-Encoding', 'identity');

      // Create fetch options
      const fetchOptions = {
        method: request.method,
        headers: forwardHeaders,
      };

      // Add body for non-GET/HEAD requests
      if (request.method !== 'GET' && request.method !== 'HEAD') {
        const body = await request.text();
        if (body) {
          fetchOptions.body = body;
          forwardHeaders.set('Content-Type', request.headers.get('Content-Type') || 'application/json');
        }
      }

      // Make the request to Akash backend
      const response = await fetch(targetUrl, fetchOptions);

      // Handle streaming response (SSE)
      if (isStreamingRequest && response.headers.get('Content-Type')?.includes('text/event-stream')) {
        return new Response(response.body, {
          status: response.status,
          headers: {
            ...corsHeaders,
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
          },
        });
      }

      // Standard response
      const responseBody = await response.text();
      
      return new Response(responseBody, {
        status: response.status,
        headers: {
          ...corsHeaders,
          'Content-Type': response.headers.get('Content-Type') || 'application/json',
        },
      });

    } catch (error) {
      console.error('Proxy error:', error.message, error.stack);
      return new Response(
        JSON.stringify({ 
          error: 'Proxy error', 
          message: 'Failed to connect to backend service',
          details: error.message 
        }),
        { status: 502, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }
  },
};
