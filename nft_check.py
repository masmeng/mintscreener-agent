#!/usr/bin/env python3
"""Optional NFT mode: Element collection floor / volume check (read-only).

Reuses the working Element GraphQL helper the user already verified
(`~/workspace/goals/sellable-nft-sale/hidden_files/el_floors.py`,
`floor_for()`: contract -> slug -> collection stats). This file adds no new
credentials and no new network logic — it only imports that helper and
applies the same buyer-proof verdict rule the token screener uses:

  totalVolume > 0  -> "SOLD BEFORE" — at least one real sale happened.
  volume == 0      -> "LISTED, NEVER SOLD" — the floor is only the cheapest
                      ask; nobody has paid it. Do not treat it as a price.
  no collection    -> "NOT ON ELEMENT" — nothing listed at all.

A floor price is NEVER a sale price. Volume 0 means the floor is unproven.

Usage:
  python nft_check.py 0x1cf9e60218493149ACe7DC953497c07175aa625e --label "Wise Owl Society"
  python nft_check.py --holdings nft_holdings.json
  # nft_holdings.json: [{"name": "...", "contract": "0x..."}, ...]
"""
import argparse
import json
import sys

sys.path.insert(0, "/home/hatch/workspace/goals/sellable-nft-sale/hidden_files")
from el_floors import floor_for  # noqa: E402  (verified working helper, 2026-11-09)


def verdict(stats):
    if stats is None:
        return "NOT ON ELEMENT", "no collection found for this contract"
    vol = stats.get("total_volume_bnb") or 0
    if vol > 0:
        return ("SOLD BEFORE",
                f"totalVolume {vol} BNB — at least one real sale happened")
    return ("LISTED, NEVER SOLD",
            f"floor {stats.get('floor_bnb')} BNB is only the cheapest ask; "
            f"totalVolume 0 means nobody has paid it")


def check(contract, label):
    stats = floor_for(contract)
    v, reason = verdict(stats)
    print(f"== {label}  {contract} ==")
    if stats is None:
        print("  Element: no collection found")
    else:
        print(f"  slug={stats['slug']} items={stats['items']} "
              f"floor={stats['floor_bnb']} BNB (~${stats['usd']}) "
              f"totalVolume={stats['total_volume_bnb']} BNB")
    print(f"  VERDICT: {v} — {reason}")
    return {"label": label, "contract": contract, "stats": stats,
            "verdict": v, "reason": reason}


def main(argv=None):
    ap = argparse.ArgumentParser(description="NFT floor/volume check (Element, read-only).")
    ap.add_argument("contract", nargs="?", help="ERC-721 contract address")
    ap.add_argument("--label", default=None)
    ap.add_argument("--holdings", help="JSON list of {name, contract}")
    args = ap.parse_args(argv)

    targets = []
    if args.holdings:
        with open(args.holdings) as f:
            for h in json.load(f):
                targets.append((h["contract"], h["name"]))
    elif args.contract:
        targets.append((args.contract, args.label or args.contract))
    else:
        ap.error("give a contract address or --holdings nft_holdings.json")

    results = [check(c, label) for c, label in targets]
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("SUMMARY: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
          + f"  (n={len(results)})")
    print("Read-only: no keys, no transactions. A floor is an ask, not a sale.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
