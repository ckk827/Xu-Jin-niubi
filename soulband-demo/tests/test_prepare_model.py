"""Download TLS regressions with a local HTTPS server, without model downloads."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_model


class DownloadTlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="soulband-download-tls-")
        root = Path(cls.directory.name)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=1))
                .not_valid_after(now + timedelta(days=1))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
                .sign(key, hashes.SHA256()))
        cls.ca = root / "test-ca.pem"
        cls.ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        private = root / "test-key.pem"
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                             serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/asset")
                else:
                    self.send_response(200)
                self.end_headers()
                if self.path != "/redirect":
                    self.wfile.write(b"verified asset")

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cls.ca, private)
        cls.server.socket = server_context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.directory.cleanup()

    def test_ca_bundle_works_when_default_store_has_no_issuer_and_after_redirect(self):
        empty_store = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with patch.object(prepare_model.ssl, "create_default_context", return_value=empty_store), \
                patch.object(prepare_model.certifi, "where", return_value=str(self.ca)):
            with prepare_model.open_download(f"https://localhost:{self.port}/redirect", timeout=3) as response:
                self.assertEqual(response.read(), b"verified asset")
                self.assertTrue(response.url.endswith("/asset"))
        self.assertEqual(empty_store.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(empty_store.check_hostname)

    def test_untrusted_certificate_is_rejected(self):
        with self.assertRaises(urllib.error.URLError) as caught:
            prepare_model.open_download(f"https://localhost:{self.port}/asset", timeout=3)
        self.assertIsInstance(caught.exception.reason, ssl.SSLCertVerificationError)

    def test_trusted_certificate_with_wrong_hostname_is_rejected(self):
        with patch.object(prepare_model.certifi, "where", return_value=str(self.ca)):
            with self.assertRaises(urllib.error.URLError) as caught:
                prepare_model.open_download(f"https://127.0.0.1:{self.port}/asset", timeout=3)
        self.assertIsInstance(caught.exception.reason, ssl.SSLCertVerificationError)


if __name__ == "__main__":
    unittest.main()
