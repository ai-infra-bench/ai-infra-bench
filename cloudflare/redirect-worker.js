const STATIC_HTML_ROUTE = /^\/(?:index|leaderboard|tasks(?:\/[^/]+)?)\.html$/;

function cleanPath(pathname) {
  if (pathname === '/index.html') return '/';
  return pathname.slice(0, -'.html'.length);
}

const worker = {
  async fetch(request) {
    const url = new URL(request.url);

    if ((request.method === 'GET' || request.method === 'HEAD') && STATIC_HTML_ROUTE.test(url.pathname)) {
      url.pathname = cleanPath(url.pathname);
      return Response.redirect(url.toString(), 301);
    }

    return globalThis.fetch(request);
  },
};

export default worker;
