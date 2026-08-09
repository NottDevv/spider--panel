"""OpenVPN PKI + config generation for the Spider panel.

All artifacts live in <DATA_DIR>/openvpn/. Key invariants:

- ensure_pki() / ensure_client() only generate what is MISSING. Editing the
  external TCP-proxy domain/port (the fields users actually change) never
  regenerates CA / server / client keys or certs — those are stable so client
  .ovpn profiles keep working across edits.
- The server.conf listens on 0.0.0.0:{internal_listen_port}. The external
  domain/port NEVER appear in server.conf; they only appear in the client
  .ovpn as `remote {ext_domain} {ext_port}`.
"""

import datetime
import os
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CA_CN = "Spider OpenVPN CA"
SERVER_CN = "server"
VALIDITY_DAYS = 3650
KEY_SIZE = 2048


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)

_lock = threading.RLock()  # reentrant: ensure_client calls ensure_pki while holding it
_config = {"dir": None}  # set by init_openvpn()


def init_openvpn(base_dir):
    """Point the module at a data directory (call once at startup)."""
    d = Path(base_dir) / "openvpn"
    d.mkdir(parents=True, exist_ok=True)
    (d / "clients").mkdir(parents=True, exist_ok=True)
    _config["dir"] = d
    return d


def _dir() -> Path:
    d = _config.get("dir")
    if d is None:
        d = init_openvpn(os.environ.get("DATA_DIR", "/data"))
    return d


def _write(path: Path, data: bytes, mode: int = 0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, mode)


def _load_key(path: Path):
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _load_cert(path: Path):
    return x509.load_pem_x509_certificate(path.read_bytes())


def ensure_pki() -> dict:
    """Idempotently create the CA + server key/cert pair. Returns their paths."""
    d = _dir()
    ca_crt, ca_key = d / "ca.crt", d / "ca.key"
    srv_crt, srv_key = d / "server.crt", d / "server.key"
    with _lock:
        if not (ca_crt.exists() and ca_key.exists()):
            key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)
            subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, CA_CN)])
            now = x509.random_serial_number()
            builder = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(subject)
                .public_key(key.public_key())
                .serial_number(now)
                .not_valid_before(_utcnow() - datetime.timedelta(days=1))
                .not_valid_after(_utcnow() + datetime.timedelta(days=VALIDITY_DAYS))
            )
            builder = builder.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            builder = builder.add_extension(
                x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
                              data_encipherment=False, key_agreement=False, key_cert_sign=True,
                              crl_sign=True, encipher_only=False, decipher_only=False),
                critical=True,
            )
            builder = builder.add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False,
            )
            cert = builder.sign(key, hashes.SHA256())
            _write(ca_key, key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ), 0o600)
            _write(ca_crt, cert.public_bytes(serialization.Encoding.PEM))

        if not (srv_crt.exists() and srv_key.exists()):
            key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)
            subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SERVER_CN)])
            ca_key_obj = _load_key(ca_key)
            ca_cert_obj = _load_cert(ca_crt)
            builder = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(ca_cert_obj.subject)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(_utcnow() - datetime.timedelta(days=1))
                .not_valid_after(_utcnow() + datetime.timedelta(days=VALIDITY_DAYS))
            )
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False,
            )
            builder = builder.add_extension(
                x509.SubjectAlternativeName([x509.DNSName("server")]), critical=False,
            )
            cert = builder.sign(ca_key_obj, hashes.SHA256())
            _write(srv_key, key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ), 0o600)
            _write(srv_crt, cert.public_bytes(serialization.Encoding.PEM))

    return {"ca_crt": str(ca_crt), "ca_key": str(ca_key),
            "server_crt": str(srv_crt), "server_key": str(srv_key)}


def ensure_client(user_id: str, username: str) -> dict:
    """Idempotently create a per-user client key/cert signed by the CA.

    Reuses an existing cert for user_id so a regenerated .ovpn keeps the same
    identity. Returns {"crt": path, "key": path}.
    """
    d = _dir()
    cl = d / "clients"
    crt, key = cl / f"{user_id}.crt", cl / f"{user_id}.key"
    if crt.exists() and key.exists():
        return {"crt": str(crt), "key": str(key)}
    with _lock:
        if crt.exists() and key.exists():
            return {"crt": str(crt), "key": str(key)}
        ensure_pki()
        ca_cert_obj = _load_cert(d / "ca.crt")
        ca_key_obj = _load_key(d / "ca.key")
        k = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)
        cn = username[:64] or user_id
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert_obj.subject)
            .public_key(k.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(ca_cert_obj.not_valid_before_utc)
            .not_valid_after(ca_cert_obj.not_valid_after_utc)
        )
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False,
        )
        cert = builder.sign(ca_key_obj, hashes.SHA256())
        _write(key, k.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ), 0o600)
        _write(crt, cert.public_bytes(serialization.Encoding.PEM))
    return {"crt": str(crt), "key": str(key)}


def build_server_conf(internal_port: int) -> str:
    """Render server.conf for 0.0.0.0:{internal_port}. External proxy settings
    never appear here."""
    d = _dir()
    ensure_pki()
    return (
        f"port {int(internal_port)}\n"
        "proto tcp\n"
        "dev tun\n"
        # DCO needs a kernel module that container hosts (Railway) may lack;
        # force the classic tun driver so any host with /dev/net/tun works.
        "disable-dco\n"
        f"ca {d / 'ca.crt'}\n"
        f"cert {d / 'server.crt'}\n"
        f"key {d / 'server.key'}\n"
        "server 10.8.0.0 255.255.255.0\n"
        "topology subnet\n"
        "keepalive 10 120\n"
        "cipher AES-256-GCM\n"
        "data-ciphers AES-256-GCM\n"
        "auth SHA256\n"
        "persist-key\n"
        "persist-tun\n"
        "verb 3\n"
    )


def write_server_conf(internal_port: int) -> Path:
    path = _dir() / "server.conf"
    path.write_text(build_server_conf(internal_port))
    return path


def build_ovpn(user_id: str, username: str, ext_domain: str, ext_port: int) -> str:
    """Render a client .ovpn. `remote` is always {ext_domain} {ext_port} — never
    the internal listen port. Raises ValueError when the external endpoint is
    not configured."""
    ext_domain = (ext_domain or "").strip()
    if not ext_domain:
        raise ValueError("external_tcp_proxy_domain is not set")
    if not ext_port:
        raise ValueError("external_tcp_proxy_port is not set")
    creds = ensure_client(user_id, username)
    ca_cert = (_dir() / "ca.crt").read_text()
    client_cert = Path(creds["crt"]).read_text()
    client_key = Path(creds["key"]).read_text()
    return (
        "client\n"
        "dev tun\n"
        "proto tcp-client\n"
        f"remote {ext_domain} {int(ext_port)}\n"
        "resolv-retry infinite\n"
        "nobind\n"
        "persist-key\n"
        "persist-tun\n"
        "remote-cert-tls server\n"
        "cipher AES-256-GCM\n"
        "data-ciphers AES-256-GCM\n"
        "auth SHA256\n"
        "auth-nocache\n"
        "verb 3\n"
        "<ca>\n" + ca_cert + "</ca>\n"
        "<cert>\n" + client_cert + "</cert>\n"
        "<key>\n" + client_key + "</key>\n"
    )
