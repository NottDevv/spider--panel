#!/usr/bin/env python3
"""
Fetch real HTTP/SOCKS5 proxy IPs, verify they actually work as proxies
(CONNECT to cloudflare.com and read /cdn-cgi/trace, exactly like the BPB
worker's proxy test), geo-locate each working proxy's egress IP, and write it
into data/country_proxies/<CC>.txt.

On every run the country proxy files are REBUILT from scratch — old entries
are wiped so the panel always reflects the current live pool.

Usage:
    .venv/bin/python fetch_proxies.py                 # fetch + verify + geo + save
    .venv/bin/python fetch_proxies.py --limit 300     # cap candidate count
"""
import asyncio
import argparse
import random
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent
PROXY_DIR = BASE / "data" / "country_proxies"
PROXY_DIR.mkdir(parents=True, exist_ok=True)

# Files that are not per-country (keep them, don't wipe/parse as countries)
_NON_COUNTRY = {"01_last_update.txt", "02_proxies.csv", "03_proxies.txt"}

CONNECT_TEST_HOST = "cloudflare.com"
CONNECT_TEST_PORT = 443
CONNECT_TIMEOUT = 4.0
MAX_CONCURRENT = 25
GEO_BATCH = 100  # ip-api.com allows 100 IPs per batch POST

# Free sources of proxy lists (raw text, "host:port" per line)
SOURCES = [
    "https://api.proxyscrape.com/v3/free-proxy-list/get?request=display_proxies&protocol=http&timeout=5000&country=all",
    "https://api.proxyscrape.com/v3/free-proxy-list/get?request=display_proxies&protocol=socks5&timeout=5000&country=all",
    "https://proxylist.geonode.com/api/proxy-list?limit=300&page=1&sort_by=lastChecked&sort_type=desc&protocols=http",
    "https://proxylist.geonode.com/api/proxy-list?limit=300&page=1&sort_by=lastChecked&sort_type=desc&protocols=socks5",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def wipe_country_files():
    """Remove every per-country file so the pool is rebuilt from scratch."""
    removed = 0
    for f in PROXY_DIR.glob("*.txt"):
        if f.name in _NON_COUNTRY:
            continue
        f.unlink(missing_ok=True)
        removed += 1
    print(f"[i] cleared {removed} old country file(s)")


def parse_candidates(text: str):
    """Extract host:port candidates from a raw body (handles json or text)."""
    out = []
    t = text.strip()
    if not t:
        return out
    if t.startswith("[") or t.startswith("{"):
        try:
            import json
            data = json.loads(t)
        except Exception:
            data = None
        if isinstance(data, dict):
            items = data.get("data") or []
            for it in items:
                ip = it.get("ip")
                port = it.get("port")
                proto = it.get("protocols", [""])
                if ip and port:
                    proto_str = proto[0] if isinstance(proto, list) and proto else str(proto)
                    p = str(port)
                    out.append(f"{proto_str}://{ip}:{p}" if "socks" in str(proto_str) else f"{ip}:{p}")
            return out
        if isinstance(data, list):
            return out
    for line in t.splitlines():
        line = line.strip()
        if not line:
            continue
        for pr in ("http://", "https://", "socks5://", "socks4://"):
            if line.lower().startswith(pr):
                rest = line[len(pr):]
                if pr.startswith("socks"):
                    out.append(f"{pr}{rest}")
                else:
                    out.append(rest)
                break
        else:
            out.append(line)
    return out


async def fetch_candidates(client: httpx.AsyncClient):
    cands = []
    for url in SOURCES:
        try:
            r = await client.get(url, timeout=10.0, follow_redirects=True)
            if r.status_code == 200:
                parsed = parse_candidates(r.text)
                if parsed:
                    print(f"[+] {url.split('/')[2]:28} -> {len(parsed)} candidates")
                    cands.extend(parsed)
        except Exception as e:
            print(f"[-] {url.split('/')[2]:28} error: {e}")
    seen, uniq = set(), []
    for c in cands:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


async def try_connect_through(proxy_host: str, proxy_port: int, proto: str):
    """Try to open a CONNECT tunnel to cloudflare.com through the proxy.

    Returns (ok, egress_ip, latency_ms) — egress_ip from /cdn-cgi/trace
    confirms the proxy actually routes traffic.
    """
    try:
        rdr, wtr = await asyncio.wait_for(
            asyncio.open_connection(proxy_host, proxy_port), timeout=CONNECT_TIMEOUT
        )
    except Exception:
        return False, "", 0
    t0 = time.time()
    try:
        if proto == "socks5":
            wtr.write(b"\x05\x01\x00")
            await wtr.drain()
            resp = await asyncio.wait_for(rdr.readexactly(2), timeout=CONNECT_TIMEOUT)
            if resp[1] != 0x00:
                return False, "", 0
            eb = CONNECT_TEST_HOST.encode()
            pkt = (b"\x05\x01\x00\x03" + bytes([len(eb)]) + eb +
                   bytes([CONNECT_TEST_PORT >> 8, CONNECT_TEST_PORT & 0xFF]))
            wtr.write(pkt)
            await wtr.drain()
            hdr = await asyncio.wait_for(rdr.readexactly(4), timeout=CONNECT_TIMEOUT)
            if hdr[1] != 0x00:
                return False, "", 0
            atyp = hdr[3]
            if atyp == 0x01:
                await asyncio.wait_for(rdr.readexactly(6), timeout=CONNECT_TIMEOUT)
            elif atyp == 0x04:
                await asyncio.wait_for(rdr.readexactly(18), timeout=CONNECT_TIMEOUT)
            elif atyp == 0x03:
                ln = (await asyncio.wait_for(rdr.readexactly(1), timeout=CONNECT_TIMEOUT))[0]
                await asyncio.wait_for(rdr.readexactly(ln + 2), timeout=CONNECT_TIMEOUT)
        else:
            req = (f"CONNECT {CONNECT_TEST_HOST}:{CONNECT_TEST_PORT} HTTP/1.1\r\n"
                   f"Host: {CONNECT_TEST_HOST}:{CONNECT_TEST_PORT}\r\n"
                   f"User-Agent: {USER_AGENT}\r\nConnection: keep-alive\r\n\r\n")
            wtr.write(req.encode())
            await wtr.drain()
            status = await asyncio.wait_for(rdr.readline(), timeout=CONNECT_TIMEOUT)
            while True:
                line = await asyncio.wait_for(rdr.readline(), timeout=CONNECT_TIMEOUT)
                if line in (b"\r\n", b"\n", b""):
                    break
            if b"200" not in status:
                return False, "", 0

        wtr.write(b"GET /cdn-cgi/trace HTTP/1.1\r\nHost: cloudflare.com\r\n"
                  b"User-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n")
        await wtr.drain()
        buf = b""
        try:
            while True:
                chunk = await asyncio.wait_for(rdr.read(2048), timeout=CONNECT_TIMEOUT)
                if not chunk:
                    break
                buf += chunk
                if b"ip=" in buf:
                    break
        except Exception:
            pass
        egress = ""
        for line in buf.split(b"\n"):
            if line.startswith(b"ip="):
                egress = line[3:].decode("utf-8", "ignore").strip()
                break
        latency = int((time.time() - t0) * 1000)
        if egress:
            return True, egress, latency
        return False, "", latency
    except Exception:
        return False, "", 0
    finally:
        try:
            wtr.close()
        except Exception:
            pass


async def verify_proxy(candidate: str):
    """candidate: 'ip:port' or 'socks5://ip:port'. Returns dict or None."""
    proto = "http"
    s = candidate.strip()
    if s.lower().startswith("socks"):
        proto = "socks5"
        s = s.split("://", 1)[1] if "://" in s else s
    if "@" in s:
        s = s.rsplit("@", 1)[1]
    if ":" in s:
        host, _, port_s = s.rpartition(":")
    else:
        host, port_s = s, "80"
    try:
        port = int(port_s)
    except ValueError:
        return None
    ok, egress, latency = await try_connect_through(host, port, proto)
    if ok:
        return {"host": host, "port": port, "proto": proto, "egress": egress, "latency": latency}
    return None


async def geo_locate_egress(client: httpx.AsyncClient, egress_ips):
    """Return {egress_ip: countryCode} via ip-api.com batch (100 per call)."""
    mapping = {}
    for i in range(0, len(egress_ips), GEO_BATCH):
        batch = egress_ips[i:i + GEO_BATCH]
        try:
            r = await client.post(
                "http://ip-api.com/batch?fields=query,countryCode,status",
                json=batch,
            )
            if r.status_code == 200:
                for item in r.json():
                    if item.get("status") == "success":
                        mapping[item["query"]] = (item.get("countryCode") or "ZZ").upper()
        except Exception:
            continue
    return mapping


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap candidate count (0=all)")
    args = ap.parse_args()

    # Start fresh: remove all old per-country files.
    wipe_country_files()

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=10.0) as client:
        candidates = await fetch_candidates(client)
        if args.limit and len(candidates) > args.limit:
            candidates = random.sample(candidates, args.limit)
    print(f"[i] total unique candidates: {len(candidates)}")

    print("[i] verifying proxies (CONNECT -> cloudflare /cdn-cgi/trace)...")
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def guarded(c):
        async with sem:
            return await verify_proxy(c)

    results = await asyncio.gather(*(guarded(c) for c in candidates))
    working = [r for r in results if r]
    print(f"[+] working proxies: {len(working)} / {len(candidates)}")

    # Geo-locate each working proxy's egress IP so it lands in the right
    # country file. Keep every proxy (multiple proxies can share an egress IP).
    cc_for = {}
    if working:
        egress_ips = list(dict.fromkeys(w["egress"] for w in working))
        async with httpx.AsyncClient(timeout=8.0) as gc:
            cc_for = await geo_locate_egress(gc, egress_ips)

    by_cc = {}
    unknown = 0
    for w in working:
        cc = cc_for.get(w["egress"], "ZZ")
        if cc == "ZZ":
            unknown += 1
        by_cc.setdefault(cc, []).append(f"{w['host']} {w['port']}")

    total_written = 0
    for cc, lines in sorted(by_cc.items()):
        fname = PROXY_DIR / f"{cc}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        total_written += len(lines)
        print(f"[+] {len(lines):4} proxies -> {cc}.txt")

    with open(PROXY_DIR / "01_last_update.txt", "w", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S"))

    print(f"[i] done: {total_written} proxies into {len(by_cc)} countries "
          f"({unknown} had unknown country -> ZZ.txt)")


if __name__ == "__main__":
    asyncio.run(main())
