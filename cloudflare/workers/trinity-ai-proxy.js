// Trinity API Proxy Worker - Phase 2
// This proxies HTTPS requests to your HTTP Akash backend with ICP authentication

const AKASH_BACKEND = 'http://r2s5qh8sdpfa30mr81c4fefeps.ingress.a100.dsm.val.akash.pub';

// Allowed origins (your frontend URLs)
const ALLOWED_ORIGINS = [
  'https://trinityai.cc',
  'https://www.trinityai.cc',
  'https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io',
  'http://localhost:8000', // For local testing
];

// Routes that require ICP authentication
const PROTECTED_ROUTES = [
  '/chat/autosave',
  '/chat/list',
  '/chat/',  // /chat/{id} variants
  '/user/',  // /user/memory
];

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  const url = new URL(request.url);
  const origin = request.headers.get('Origin');
  const pathname = url.pathname;
  
  // Handle CORS preflight
  if (request.method === 'OPTIONS') {
    return handleCORS(origin);
  }
  
  // Check if route is protected (requires authentication)
  const isProtected = PROTECTED_ROUTES.some(route => pathname.startsWith(route));
  
  if (isProtected) {
    // Verify ICP authentication headers
    const principal = request.headers.get('ICP-Principal');
    const signature = request.headers.get('ICP-Signature');
    const timestamp = request.headers.get('ICP-Timestamp');
    const publicKey = request.headers.get('ICP-PublicKey');
    
    if (!principal || !signature || !timestamp) {
      return new Response(JSON.stringify({
        error: 'Missing authentication headers',
        required: ['ICP-Principal', 'ICP-Signature', 'ICP-Timestamp', 'ICP-PublicKey']
      }), {
        status: 401,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': ALLOWED_ORIGINS.includes(origin) ? origin : '',
        }
      });
    }
    
    // Verify timestamp is recent (within 5 minutes)
    const requestTime = parseInt(timestamp);
    const currentTime = Date.now();
    const timeDiff = Math.abs(currentTime - requestTime);
    
    if (timeDiff > 5 * 60 * 1000) {  // 5 minutes
      return new Response(JSON.stringify({
        error: 'Timestamp too old'
      }), {
        status: 401,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': ALLOWED_ORIGINS.includes(origin) ? origin : '',
        }
      });
    }
  }
  
  // Allow all endpoints now
  const allowedPaths = [
    '/health',
    '/generate',
    '/stats',
    '/chat/autosave',
    '/chat/list',
    '/chat/',  // catch /chat/xxx
    '/user/',  // catch /user/memory
  ];
  
  // Check if path is allowed (simple prefix matching for /chat/ and /user/ routes)
  const isAllowed = allowedPaths.some(path => {
    if (path === '/chat/') {
      return pathname.startsWith('/chat/');
    }
    if (path === '/user/') {
      return pathname.startsWith('/user/');
    }
    return pathname === path;
  });
  
  if (!isAllowed) {
    return new Response(JSON.stringify({
      error: 'Endpoint not found',
      available: allowedPaths
    }), {
      status: 404,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': ALLOWED_ORIGINS.includes(origin) ? origin : '',
      }
    });
  }
  
  // Build the Akash backend URL
  const backendUrl = AKASH_BACKEND + pathname + url.search;
  
  // Forward the request to Akash
  try {
    let requestBody = undefined;
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      requestBody = await request.text();
    }
    
    const backendRequest = new Request(backendUrl, {
      method: request.method,
      headers: request.headers,
      body: requestBody,
    });
    
    const response = await fetch(backendRequest);
    
    // Clone response and add CORS headers
    const newResponse = new Response(response.body, response);
    
    // Add CORS headers
    if (ALLOWED_ORIGINS.includes(origin)) {
      newResponse.headers.set('Access-Control-Allow-Origin', origin);
    }
    newResponse.headers.set('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
    newResponse.headers.set('Access-Control-Allow-Headers', 'Content-Type, Accept, ICP-Principal, ICP-Signature, ICP-Timestamp, ICP-PublicKey');
    newResponse.headers.set('Access-Control-Max-Age', '86400');
    
    return newResponse;
    
  } catch (error) {
    return new Response(JSON.stringify({
      error: 'Backend unavailable',
      message: error.message
    }), {
      status: 503,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': ALLOWED_ORIGINS.includes(origin) ? origin : '',
      }
    });
  }
}

function handleCORS(origin) {
  const headers = {
    'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept, ICP-Principal, ICP-Signature, ICP-Timestamp, ICP-PublicKey',
    'Access-Control-Max-Age': '86400',
  };
  
  if (ALLOWED_ORIGINS.includes(origin)) {
    headers['Access-Control-Allow-Origin'] = origin;
  }
  
  return new Response(null, { headers });
}