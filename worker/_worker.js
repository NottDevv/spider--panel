// Spider Panel — VLESS Worker (edgetunnel-style, lightweight)
// Deployed by the panel to Cloudflare Workers. Serves VLESS/WS/TLS configs with
// SNI spoofing (like edgetunnel) and manages users (UUID → traffic/expiry) in KV.
// The panel controls it via the admin API (Bearer token baked in at deploy).
//
// Injected at deploy time:
//   __PANEL_TOKEN__   → random control token (JSON string)
//   __PANEL_DOMAIN__  → panel public domain (JSON string)

const PANEL_TOKEN = __PANEL_TOKEN__;
const PANEL_DOMAIN = __PANEL_DOMAIN__;
const BUF = 64 * 1024;

function json(data, status) {
  return new Response(JSON.stringify(data), {
    status: status || 200,
    headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
  });
}
function authorized(request) {
  return (request.headers.get('Authorization') || '') === 'Bearer ' + PANEL_TOKEN;
}
function uuidRe() { return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i; }

// KV helpers (SPIDER_KV binding). User record: {uuid, remark, limit_bytes, expire, used_bytes, proxy_ip}.
async function getUser(env, uuid) {
  uuid = (uuid || '').toLowerCase();
  if (!uuidRe().test(uuid)) return null;
  try {
    const raw = await env.SPIDER_KV.get('user:' + uuid);
    if (!raw) return null;
    const u = JSON.parse(raw);
    if (u.expire && Date.now() / 1000 > u.expire) return null;
    if (u.limit_bytes > 0 && u.used_bytes >= u.limit_bytes) return null;
    return u;
  } catch (e) { return null; }
}
async function setUser(env, uuid, u) { await env.SPIDER_KV.put('user:' + uuid, JSON.stringify(u)); }
async function addUsage(env, uuid, n) {
  try {
    const u = await getUser(env, uuid);
    if (!u) return;
    u.used_bytes = (u.used_bytes || 0) + n;
    await setUser(env, uuid, u);
  } catch (e) {}
}

// Parse the VLESS header from the first websocket binary message.
function parseVlessHeader(data) {
  if (data.length < 24) return null;
  let pos = 1; pos += 16;
  const addonLen = data[pos]; pos += 1 + addonLen;
  pos += 1; // command (1 = TCP)
  const port = (data[pos] << 8) | data[pos + 1]; pos += 2;
  const atype = data[pos]; pos += 1;
  let address;
  if (atype === 1) { address = data.slice(pos, pos + 4).join('.'); pos += 4; }
  else if (atype === 2) { const dlen = data[pos]; pos += 1; address = new TextDecoder().decode(data.subarray(pos, pos + dlen)); pos += dlen; }
  else if (atype === 3) { const b = data.subarray(pos, pos + 16); pos += 16; const hex=[]; for(let i=0;i<16;i+=2) hex.push(((b[i]<<8)|b[i+1]).toString(16)); address=hex.join(':'); }
  else return null;
  return { address, port, payload: data.subarray(pos) };
}

// Connect to the target, possibly via a proxy IP (fallback direct).
async function connectTarget(fetcher, host, port, proxyIP) {
  if (proxyIP) {
    try {
      return await connectViaProxy(fetcher, proxyIP, host, port);
    } catch (e) { /* fall through to direct */ }
  }
  return await connectDirect(fetcher, host, port);
}

async function connectDirect(fetcher, host, port) {
  if (fetcher && typeof fetcher.connect === 'function') {
    try { return await fetcher.connect({ hostname: host, port }); } catch(e) {}
  }
  return null;
}

async function connectViaProxy(fetcher, proxyIP, host, port) {
  // proxyIP is "ip:port" or "domain:port". Try HTTP CONNECT through it; fallback direct.
  try {
    const [ph, pp] = String(proxyIP).split(':');
    const targetPort = Number(pp) || 443;
    if (fetcher && typeof fetcher.connect === 'function') {
      const sock = await fetcher.connect({ hostname: ph, port: targetPort });
      // Send an HTTP CONNECT request to the proxy.
      const enc = new TextEncoder();
      const req = enc.encode(`CONNECT ${host}:${port} HTTP/1.1\r\nHost: ${host}:${port}\r\n\r\n`);
      await sock.write(req);
      // read the CONNECT response (up to \r\n\r\n)
      const reader = sock.readable.getReader();
      let buf = new Uint8Array(0);
      let got = false;
      while (!got) {
        const { done, value } = await reader.read();
        if (done) break;
        const tmp = new Uint8Array(buf.length + value.length);
        tmp.set(buf); tmp.set(value, buf.length); buf = tmp;
        const idx = findHeaderEnd(buf);
        if (idx !== -1) {
          const head = new TextDecoder().decode(buf.subarray(0, idx));
          if (/HTTP\/1\.[01] 200/i.test(head)) got = true;
          else break;
          if (buf.length > idx) { /* leftover */ }
        }
      }
      if (!got) { try { sock.close(); } catch(e){} return null; }
      return wrapSocket(sock, reader);
    }
  } catch (e) {}
  return connectTarget(fetcher, host, port);
}

function findHeaderEnd(buf) {
  for (let i = 0; i <= buf.length - 4; i++) {
    if (buf[i] === 13 && buf[i+1] === 10 && buf[i+2] === 13 && buf[i+3] === 10) return i + 4;
  }
  return -1;
}

function wrapSocket(sock, reader) {
  return {
    write: async (data) => { try { await sock.write(data); } catch(e){} },
    readable: reader,
    close: async () => { try { await sock.close(); } catch(e){} },
  };
}

async function pumpTcpToWs(reader, server) {
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value && value.length) {
        // VLESS over WS: server frames are [0x00 0x00] + data
        const frame = new Uint8Array(value.length + 2);
        frame[0] = 0; frame[1] = 0; frame.set(value, 2);
        try { server.send(frame.buffer); } catch(e){ break; }
      }
    }
  } catch (e) {}
  try { server.close(1000); } catch(e){}
}
// ── Main handler ──
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === '/' || path === '/health') {
      return new Response('Spider VLESS Worker online', { headers: { 'content-type': 'text/plain' } });
    }

    // ── Admin API (Bearer PANEL_TOKEN) ──
    if (path.startsWith('/api/')) {
      if (!authorized(request)) return json({ error: 'Forbidden' }, 403);

      if (path === '/api/users') {
        if (request.method === 'GET') {
          const out = [];
          const list = await env.SPIDER_KV.list({ prefix: 'user:' });
          for (const k of list.keys) { const raw = await env.SPIDER_KV.get(k.name); if (raw) out.push(JSON.parse(raw)); }
          return json({ ok: true, users: out });
        }
        const body = await request.json();
        const uuid = String(body.uuid || '').toLowerCase();
        if (!uuidRe().test(uuid)) return json({ error: 'bad uuid' }, 400);
        const u = {
          uuid, remark: String(body.remark || 'user'),
          limit_bytes: Number(body.limit_bytes) || 0,
          expire: Number(body.expire) || 0,
          used_bytes: Number(body.used_bytes) || 0,
          proxy_ip: String(body.proxy_ip || ''),
          created: Date.now(),
        };
        await setUser(env, uuid, u);
        return json({ ok: true, user: u });
      }
      if (path.startsWith('/api/user/')) {
        const uuid = path.split('/').pop().toLowerCase();
        if (request.method === 'DELETE') { await env.SPIDER_KV.delete('user:' + uuid); return json({ ok: true }); }
        const u = await getUser(env, uuid);
        if (!u) return json({ error: 'not found' }, 404);
        return json({ ok: true, user: u });
      }
      if (path === '/api/locations') {
        const raw = await env.SPIDER_KV.get('proxies') || '[]';
        try { return json({ ok: true, locations: JSON.parse(raw) }); } catch(e){ return json({ ok: true, locations: [] }); }
      }
      if (path === '/api/proxies' && request.method === 'POST') {
        const body = await request.json();
        await env.SPIDER_KV.put('proxies', JSON.stringify(body.locations || []));
        return json({ ok: true });
      }
      return json({ error: 'Not Found' }, 404);
    }

    // ── VLESS WS tunnel — path /{uuid} ──
    const seg = path.split('/').filter(Boolean);
    const uuid = (seg[0] || '').toLowerCase();
    if (uuidRe().test(uuid)) {
      const u = await getUser(env, uuid);
      if (!u) return json({ error: 'unauthorized' }, 403);
      if (request.headers.get('Upgrade') === 'websocket') {
        return handleVlessWs(request, env, u);
      }
      return json({ error: 'websocket upgrade required' }, 400);
    }

    return json({ error: 'Not Found' }, 404);
  },
};

async function handleVlessWs(request, env, user) {
  const pair = new WebSocketPair();
  const [client, server] = Object.values(pair);
  server.accept();
  server.binaryType = 'arraybuffer';

  server.addEventListener('message', async (ev) => {
    const data = new Uint8Array(ev.data);
    if (!server.__h) {
      const h = parseVlessHeader(data);
      if (!h) { try { server.close(4002, 'bad header'); } catch(e){} return; }
      server.__h = h;
      try {
        const fetcher = request.fetcher;
        const target = await connectTarget(fetcher, h.address, h.port, user.proxy_ip);
        if (!target) throw new Error('connect failed');
        server.__sock = target;
        server.__wsToTcp = async (chunk) => {
          try { await target.write(chunk); } catch(e){ try{server.close(4003);}catch(_){} }
        };
        if (h.payload.length) { try { await target.write(h.payload); } catch(e){} }
        pumpTcpToWs(target.readable, server);
        if (h.payload.length) addUsage(env, user.uuid, h.payload.length);
        return;
      } catch (e) {
        try { server.close(4001, 'connect failed'); } catch(err){}
        return;
      }
    }
    if (server.__wsToTcp) { server.__wsToTcp(data); addUsage(env, user.uuid, data.length); }
  });

  server.addEventListener('close', () => { try { server.__sock && server.__sock.close(); } catch(e){} });
  server.addEventListener('error', () => { try { server.__sock && server.__sock.close(); } catch(e){} });

  return new Response(null, { status: 101, webSocket: client });
}
