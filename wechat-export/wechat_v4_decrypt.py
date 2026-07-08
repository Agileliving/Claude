#!/usr/bin/env python3
"""
Decrypt WeChat 4.x (macOS) SQLCipher databases using keys already extracted from
WeChat's process memory.

Why this exists: tools like WxEcho extract the raw AES keys from memory but then
try to *match* each key to a database by comparing salts. On newer WeChat builds
(e.g. 4.1.11) that salt-matching fails ("Matched 0/N"), so decryption is skipped
even though the keys are valid. This script skips matching and simply
**brute-forces every key against every database**, confirming a hit by checking
that the decrypted page-1 header is a valid SQLite header. No HMAC math needed.

WeChat 4.x page format (per page = 4096 bytes):
    page 1 : [salt 16][ciphertext 4000][reserve 80]     (reserve = IV 16 + HMAC 64)
    page n : [ciphertext 4016][reserve 80]
The AES-256-CBC key is the raw 32-byte key from memory; the per-page IV is the
first 16 bytes of that page's 80-byte reserve. The plaintext SQLite header magic
("SQLite format 3\\0") is not stored (the salt replaces it), so we prepend it on
output and validate via the invariant header bytes at offsets 21/22/23 (64,32,32).

Usage:
    pip3 install pycryptodome
    python3 wechat_v4_decrypt.py --keys all_keys.json --db-dir "<...>/db_storage" --out ./decrypted
    # or decrypt a single file / pass keys directly:
    python3 wechat_v4_decrypt.py --key <64hexchars> --db "<...>/message/message_0.db" --out ./decrypted

`--keys` accepts WxEcho's all_keys.json (any 64-hex-char strings in it are used).
"""

import argparse
import hashlib
import json
import os
import re
import sys

PAGE_SIZE = 4096
SALT_SIZE = 16
RESERVE = 80            # IV(16) + HMAC(64)
IV_SIZE = 16
SQLITE_MAGIC = b"SQLite format 3\x00"


def _aes():
    try:
        from Crypto.Cipher import AES
        return AES
    except ImportError:
        sys.exit("pycryptodome is required. Run:  pip3 install pycryptodome")


def load_keys(args):
    """Return a list of 32-byte key candidates from --key and/or --keys file."""
    keys = []
    if args.key:
        for k in args.key:
            keys.append(bytes.fromhex(k.strip()))
    if args.keys and os.path.exists(args.keys):
        with open(args.keys, "r", encoding="utf-8", errors="replace") as fh:
            blob = fh.read()
        # Grab every 64-hex-char token (the raw AES keys), regardless of JSON shape.
        for hexstr in re.findall(r"\b[0-9a-fA-F]{64}\b", blob):
            b = bytes.fromhex(hexstr)
            if b not in keys:
                keys.append(b)
    # de-dup, keep only 32-byte keys
    uniq = []
    for k in keys:
        if len(k) == 32 and k not in uniq:
            uniq.append(k)
    return uniq


def _looks_like_sqlite_header(dec_page1_body):
    """dec_page1_body = decrypted ciphertext of page 1 (file offsets 16..4016).
    File offsets 21,22,23 are the SQLite constants 64,32,32 -> indices 5,6,7 here."""
    if len(dec_page1_body) < 8:
        return False
    return (dec_page1_body[5] == 64 and
            dec_page1_body[6] == 32 and
            dec_page1_body[7] == 32)


def try_decrypt(db_path, key):
    """Attempt to decrypt db_path with key. Returns decrypted bytes or None."""
    AES = _aes()
    with open(db_path, "rb") as fh:
        data = fh.read()
    if not data or len(data) < PAGE_SIZE:
        return None
    if data[:16] == SQLITE_MAGIC:
        return None  # already plaintext, not encrypted

    n_pages = len(data) // PAGE_SIZE
    out = bytearray()
    for i in range(n_pages):
        page = data[i * PAGE_SIZE:(i + 1) * PAGE_SIZE]
        start = SALT_SIZE if i == 0 else 0
        iv = page[PAGE_SIZE - RESERVE: PAGE_SIZE - RESERVE + IV_SIZE]
        ct = page[start: PAGE_SIZE - RESERVE]
        reserve = page[PAGE_SIZE - RESERVE:]
        if len(ct) % 16 != 0:
            return None
        dec = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
        if i == 0:
            if not _looks_like_sqlite_header(dec):
                return None  # wrong key for this DB — bail immediately
            out += SQLITE_MAGIC + dec + reserve
        else:
            out += dec + reserve
    return bytes(out)


def collect_db_files(args):
    if args.db:
        return [args.db]
    dbs = []
    for root, _dirs, files in os.walk(args.db_dir):
        for f in files:
            if f.endswith(".db"):
                dbs.append(os.path.join(root, f))
    return sorted(dbs)


def main():
    ap = argparse.ArgumentParser(description="Decrypt WeChat 4.x macOS databases with extracted keys.")
    ap.add_argument("--keys", help="Path to all_keys.json (any 64-hex keys inside are used).")
    ap.add_argument("--key", action="append", help="A raw 32-byte key as 64 hex chars (repeatable).")
    ap.add_argument("--db", help="Decrypt a single .db file.")
    ap.add_argument("--db-dir", help="Directory to search recursively for .db files (e.g. .../db_storage).")
    ap.add_argument("--out", default="./decrypted", help="Output directory for decrypted .db files.")
    args = ap.parse_args()

    keys = load_keys(args)
    if not keys:
        sys.exit("No 32-byte keys found. Pass --key <64hex> or --keys all_keys.json.")
    if not args.db and not args.db_dir:
        sys.exit("Give either --db <file> or --db-dir <db_storage directory>.")

    dbs = collect_db_files(args)
    if not dbs:
        sys.exit("No .db files found.")

    os.makedirs(args.out, exist_ok=True)
    print(f"{len(keys)} key(s), {len(dbs)} database(s). Trying every key against every DB...\n")

    ok, fail = 0, 0
    for db in dbs:
        name = os.path.basename(db)
        decrypted = None
        used = None
        for idx, key in enumerate(keys):
            try:
                decrypted = try_decrypt(db, key)
            except Exception as e:  # noqa: BLE001 - report and continue
                decrypted = None
            if decrypted:
                used = idx
                break
        if decrypted:
            outpath = os.path.join(args.out, name)
            with open(outpath, "wb") as fh:
                fh.write(decrypted)
            print(f"  OK   {name}  (key #{used})  -> {outpath}")
            ok += 1
        else:
            print(f"  --   {name}  (no matching key)")
            fail += 1

    print(f"\nDone: {ok} decrypted, {fail} not matched, {len(dbs)} total -> {args.out}")
    if ok == 0:
        print("\nNo DBs decrypted. The needed key may not be in memory yet: open the target\n"
              "conversation in WeChat (scroll it so messages load), then re-run the key\n"
              "scanner and this script.")


if __name__ == "__main__":
    main()
