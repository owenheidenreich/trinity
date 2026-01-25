// Trinity Frontend Proxy Worker
// This proxies requests from trinityai.cc to your ICP canister

const ICP_CANISTER_URL = 'https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io';

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  const url = new URL(request.url);

  // Build the ICP URL (preserve path and query string)
  const icpUrl = ICP_CANISTER_URL + url.pathname + url.search;

  // Forward the request to ICP
  const response = await fetch(icpUrl, {
    method: request.method,
    headers: request.headers,
    body: request.method !== 'GET' && request.method !== 'HEAD' ? request.body : undefined,
  });

  // Return the response
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers
  });
}