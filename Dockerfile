# Build stage: compile OpenVPN 2.7.6 from the vendored tarball.
# Builds are deterministic — no re-download, the tarball in openvpn/ is
# authoritative. The binary lands in /usr/sbin/openvpn (on PATH for root).
FROM python:3.11-slim AS openvpn-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libssl-dev liblzo2-dev liblz4-dev liblzma-dev \
        libpam0g-dev autoconf automake libtool pkg-config ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY openvpn/openvpn-2.7.6.tar.gz /tmp/openvpn-2.7.6.tar.gz

RUN mkdir -p /tmp/ovpn-src \
    && tar -xzf /tmp/openvpn-2.7.6.tar.gz -C /tmp/ovpn-src --strip-components=1 \
    && cd /tmp/ovpn-src \
    && ./configure --prefix=/usr \
    && make -j"$(nproc)" \
    && make install DESTDIR=/tmp/ovpn-install \
    && strip /tmp/ovpn-install/usr/sbin/openvpn

# Runtime stage: the panel + the compiled OpenVPN binary.
FROM python:3.11-slim

# Shared libs the openvpn binary links against on Debian bookworm.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libssl3 liblzo2-2 liblz4-1 liblzma5 libpam0g zlib1g ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=openvpn-builder /tmp/ovpn-install/usr/sbin/openvpn /usr/sbin/openvpn

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080 DATA_DIR=/data
EXPOSE 8080
CMD ["python", "main.py"]
