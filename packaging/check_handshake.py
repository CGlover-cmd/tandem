"""Run pyatv's SRP pairing handshake against srptools' server side, with the libraries as
shipped in the app folder (build_bundle.py --smoke runs it with the bundled Python).

Apple TV pairing and HomePod / AirPlay 2 connections all go through this code. 1.0.0 shipped a
srptools release that broke it, and only real hardware showed it (ADR-0017 addendum).
tests/test_dependencies.py does the same check in the dev environment.
"""

from __future__ import annotations

import binascii
import hashlib

from pyatv.auth.hap_srp import SRPAuthHandler
from srptools import SRPContext, SRPServerSession, constants


def _context(pin: str | None = None) -> SRPContext:
    return SRPContext(
        "Pair-Setup",
        pin,
        prime=constants.PRIME_3072,
        generator=constants.PRIME_3072_GEN,
        hash_func=hashlib.sha512,
    )


def main() -> None:
    pin = "1234"
    client = SRPAuthHandler()
    client.initialize()
    client.step1(pin)
    _, verifier, salt = _context(pin).get_user_data_triplet()
    server = SRPServerSession(_context(), verifier)
    pub_key, proof = client.step2(binascii.unhexlify(server.public), binascii.unhexlify(salt))
    server.process(binascii.hexlify(pub_key).decode(), salt)
    if not server.verify_proof(binascii.hexlify(proof)):
        raise SystemExit("The Apple pairing handshake failed with the shipped libraries")
    print("Apple pairing handshake works with the shipped libraries")


if __name__ == "__main__":
    main()
