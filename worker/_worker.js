// Spider Panel — Cloudflare Worker proxy (deployed by the panel)
// Template lives in the project repo (worker/_worker.js). The panel reads it at
// deploy time and injects:
//   __PROXIES_JSON__  → country → proxy map
//   __PANEL_DOMAIN__  → the panel's public domain (JSON string)
//   __PANEL_TOKEN__   → a random control token (JSON string) the panel uses to
//                       call the admin API below (Bearer auth).
// So a normal git deploy ships the Worker code, and the panel keeps control.
const PROXIES = __PROXIES_JSON__;
const PANEL_DOMAIN = __PANEL_DOMAIN__;
const PANEL_TOKEN = __PANEL_TOKEN__;

function json(data, status) {
  return new Response(JSON.stringify(data), {
    status: status || 200,
    headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
  });
}

function authorized(request) {
  const auth = request.headers.get('Authorization') || '';
  return auth === 'Bearer ' + PANEL_TOKEN;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === '/' || path === '/health') {
      return new Response('Spider Worker online', { headers: { 'content-type': 'text/plain' } });
    }

    // Public locations list (used by the panel Map/Worker tabs).
    if (path === '/api/locations') {
      return json(Object.keys(PROXIES).map(function (code) {
        const p = PROXIES[code];
        const list = p.proxies && p.proxies.length ? p.proxies : [p.proxy];
        return { country: p.country, code: code, proxy: list[0], proxies: list.length, port: p.port || 443, status: 'online', ping: 0 };
      }));
    }

    // Admin API — only the panel (Bearer PANEL_TOKEN) may call this.
    if (path === '/api/admin/update' || path === '/api/admin/sync') {
      if (!authorized(request)) return json({ error: 'Forbidden' }, 403);
      try {
        const body = await request.json();
        const newMap = body && body.proxies;
        if (newMap && typeof newMap === 'object') {
          // Rebuild PROXIES at runtime (in-memory) so the panel can push an
          // updated country → proxy map without a full re-deploy.
          Object.keys(PROXIES).forEach(function (k) { delete PROXIES[k]; });
          Object.keys(newMap).forEach(function (k) { PROXIES[k] = newMap[k]; });
          return json({ ok: true, countries: Object.keys(PROXIES).length, panel_domain: PANEL_DOMAIN });
        }
        return json({ ok: true, countries: Object.keys(PROXIES).length, panel_domain: PANEL_DOMAIN });
      } catch (e) {
        return json({ error: 'Bad JSON' }, 400);
      }
    }

    const m = path.match(/^\/route\/([a-zA-Z0-9_-]+)(\/?.*)$/);
    if (m) {
      const code = m[1].toLowerCase();
      const rest = m[2] || '';
      const target = PROXIES[code];
      if (!target) return json({ error: 'Unknown route: ' + code }, 404);

      // Prefer the multi-IP list (round-robin across IPs); fall back to .proxy.
      const list = target.proxies && target.proxies.length ? target.proxies : [target.proxy];
      const chosen = list[Math.floor(Math.random() * list.length)];

      const upstream = new URL(request.url);
      upstream.protocol = 'https:';
      upstream.hostname = chosen;
      upstream.port = String(target.port || 443);
      upstream.pathname = rest || '/';
      upstream.search = url.search;

      const headers = new Headers(request.headers);
      headers.set('Host', chosen);
      headers.set('X-Forwarded-Host', url.host);

      // Pass the original request through so WebSocket/HTTP upgrades are kept.
      return fetch(new Request(upstream.toString(), request), { headers: headers });
    }

    return json({ error: 'Not Found' }, 404);
  },
};
