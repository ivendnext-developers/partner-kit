# Sandbox certificate

`sign_sandbox_cert.py` signs your payment connector's **sandbox** certificate (a card, push or wallet connector's) with the published sandbox key, so a CitiXsys sandbox's Remote Connector record accepts your connector. The recipes that use it: [A partner wallet at the till](../../recipes/wallet.md) and [Your own card or mobile-money connector](../../recipes/payment_connector.md).

```bash
python3 samples/s22_customer_loyalty/service/wallet.py --declaration > declaration.json
python3 tools/sandbox_cert/sign_sandbox_cert.py --declaration declaration.json --partner acme --connector cash > sandbox_certificate.json
```

- The key is **public on purpose.** A CitiXsys sandbox accepts it; every production site refuses it by name.
- **A production certificate is CitiXsys's alone,** issued from your sealed conformance report. You never sign one yourself.
- Needs only Python's standard library and **OpenSSL 3.x** (which signs Ed25519). macOS's own `openssl` is LibreSSL and cannot: install OpenSSL 3 (for example with Homebrew) and put it first on your PATH.

## Technical notes

- The certificate is `{"v": 1, "kid": "test-1", "payload": P, "signature": S}`. `P` is `{"provider_key": "remote_<partner>_<connector>", "partner", "connector", "declaration", "issued"}`; `S` is the base64 Ed25519 signature over `P`'s canonical JSON (sorted keys, no spaces, ASCII).
- `tests/test_sign_sandbox_cert.py` signs a fixed payload and checks the signature twice: against the pinned bytes, and with the key's public half, the one the product holds for `test-1`.
- Source, in words: adapted from CitiXsys's private reference implementation's certificate tool @ `74c99d5`; the canonical form and the certificate's shape are copied from the iVendNext Payments code repository's remote-connector app (its certificate module) @ `7f2201d`, and the key from CitiXsys Payments' partner sandbox runbook, §4. The signing is done by `openssl`; the known-answer test holds it equal to the product's. A defect here may be a defect there: report it on the [feedback forms](../../feedback/README.md).
