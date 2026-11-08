"""Project-specific LAN CA; only its public certificate goes into client packages."""
import argparse
import ipaddress
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

ROOT = Path(__file__).resolve().parent
TLS = ROOT / "data/tls"


def prepare(directory=TLS, addresses=()):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ca_key_path, ca_path = directory / "ca.key", directory / "soulband-ca.crt"
    def write_key(path, key):
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    if ca_path.exists() != ca_key_path.exists():
        raise RuntimeError("Incomplete CA files; restore the matching backup, never silently rotate trust")
    if ca_path.exists():
        ca = x509.load_pem_x509_certificate(ca_path.read_bytes())
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        if ca.public_key().public_numbers() != ca_key.public_key().public_numbers() or ca.not_valid_after_utc <= now:
            raise RuntimeError("CA key mismatch or CA expired; explicitly rebuild client trust before rotating")
    else:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Soulband project LAN CA")])
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=1825))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
              .sign(ca_key, hashes.SHA256()))
        write_key(ca_key_path, ca_key); ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    ips = {ipaddress.ip_address(v) for v in ["127.0.0.1", "::1", *addresses]}
    cert_path, key_path = directory / "server.crt", directory / "server.key"
    if cert_path.exists() and key_path.exists():
        current = x509.load_pem_x509_certificate(cert_path.read_bytes())
        old_ips = set(current.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress))
        if ips.issubset(old_ips) and current.not_valid_after_utc > now+timedelta(days=7):
            return {"ca_sha256": ca.fingerprint(hashes.SHA256()).hex(), "ips": sorted(map(str, old_ips)), "certificate": str(cert_path)}
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Soulband LAN host")]))
            .issuer_name(ca.subject).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(minutes=5)).not_valid_after(min(now+timedelta(days=90), ca.not_valid_after_utc))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), *[x509.IPAddress(v) for v in sorted(ips,key=str)]]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    write_key(key_path, server_key); cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return {"ca_sha256": ca.fingerprint(hashes.SHA256()).hex(), "ips": sorted(map(str, ips)), "certificate": str(cert_path)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--ip", action="append", default=[])
    args = parser.parse_args(); print(json.dumps(prepare(addresses=args.ip), ensure_ascii=False))
