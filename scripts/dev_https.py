import argparse
import ipaddress
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def ensure_local_certificate(cert_dir: Path) -> tuple[Path, Path]:
    cert_dir.mkdir(parents=True, exist_ok=True)
    key_path = cert_dir / "localhost.key"
    cert_path = cert_dir / "localhost.crt"

    if key_path.exists() and cert_path.exists():
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "DZ"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Safouane Escrow Local Dev"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]
    )

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.DNSName("127.0.0.1"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    x509.IPAddress(ipaddress.ip_address("::1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def as_endpoint_path(path: Path) -> str:
    return path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Django ASGI app over HTTPS.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--cert-dir", default=".tmp-local-ssl")
    parser.add_argument("--verbosity", default="1")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)

    cert_path, key_path = ensure_local_certificate(project_root / args.cert_dir)
    endpoint = (
        f"ssl:{args.port}:"
        f"privateKey={as_endpoint_path(key_path.relative_to(project_root))}:"
        f"certKey={as_endpoint_path(cert_path.relative_to(project_root))}:"
        f"interface={args.host}"
    )

    print(f"Project root: {project_root}")
    print(f"HTTPS server: https://localhost:{args.port}/")
    print(f"Certificate: {cert_path}")
    print("Note: the browser may show a local certificate warning the first time.")

    return subprocess.call(
        [
            sys.executable,
            "-m",
            "daphne",
            "-e",
            endpoint,
            "-v",
            str(args.verbosity),
            "core.asgi:application",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
