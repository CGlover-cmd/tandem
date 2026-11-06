"""Checks that the libraries Tandem ships with still work together.

The engine's own tests use fakes for pyatv, so they can't see a dependency that breaks pyatv
underneath. 1.0.0 shipped srptools 2.0, whose new API made every Apple handshake fail; these
tests run pyatv's real SRP code (used for Apple TV pairing and for HomePod and AirPlay 2
connections) against srptools' own server side.
"""

from __future__ import annotations

import binascii
import hashlib
import re
from pathlib import Path

from pyatv.auth.hap_srp import SRPAuthHandler
from srptools import SRPContext, SRPServerSession, constants

ROOT = Path(__file__).resolve().parents[1]


def _context(pin: str | None = None) -> SRPContext:
    return SRPContext(
        "Pair-Setup",
        pin,
        prime=constants.PRIME_3072,
        generator=constants.PRIME_3072_GEN,
        hash_func=hashlib.sha512,
    )


def test_pyatv_srp_handshake_completes() -> None:
    pin = "1234"
    client = SRPAuthHandler()
    client.initialize()
    client.step1(pin)  # 1.0.0 failed here: "takes 2 positional arguments but 3 were given"

    # The device's side, from the same PIN.
    _, verifier, salt = _context(pin).get_user_data_triplet()
    server = SRPServerSession(_context(), verifier)

    pub_key, proof = client.step2(binascii.unhexlify(server.public), binascii.unhexlify(salt))
    server.process(binascii.hexlify(pub_key).decode(), salt)
    assert server.verify_proof(binascii.hexlify(proof))


def test_srptools_is_pinned_below_2() -> None:
    constraints = (ROOT / "packaging" / "constraints.txt").read_text(encoding="utf-8")
    match = re.search(r"^srptools==(\d+)\.", constraints, re.MULTILINE)
    assert match is not None
    assert int(match.group(1)) < 2
