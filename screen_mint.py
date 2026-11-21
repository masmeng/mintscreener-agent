#!/usr/bin/env python3
"""Free-mint screener for BNB Chain (BSC, chain 56) — zkVerify Agent Games, Wildcard Track.

Problem: most "free" Agent ID token mints have no buyers. Minting them burns
gas for tokens that can never be sold. This screener checks for buyer proof
ON-CHAIN before anyone mints.

Three read-only checks per token (no private keys, no transactions, no writes):
  1. Identity  — name() / symbol() / decimals() / totalSupply()
  2. PancakeSwap V2 — factory.getPair(token, WBNB); if a pair exists, read
     token0() / token1() / getReserves() and report human-readable reserves.
  3. PancakeSwap V3 — for a given pool address, slot0() + liquidity() with
     price math: price = (sqrtPriceX96 / 2**96) ** 2, adjusted for decimals
     and token0/token1 order.

Verdicts:
  BUYER PROOF  — a live pool with non-dust liquidity exists.
  WATCH        — no pool yet; nothing to sell into. Do not mint for resale.
  DEAD         — a pool exists but reserves are dust (no real liquidity).

A paper price is NEVER presented as cashable money: reserves are a proxy for
"someone could buy", not a tested sell route. 24h volume needs an indexer
and is out of scope here.

RPC notes (learned live, 2026-11-17):
  * web3.py get_block() FAILS on BSC (POA extraData) — this script never calls it.
  * bsc.publicnode.com returns HTTP 403 to web3's default UA, and rejects
    eth_getTransactionReceipt for old blocks as an "archive request"
    (needs a personal token). Fix: send a Chrome User-Agent, and fall back
    to bsc-dataseed.binance.org for receipts / any call publicnode refuses.
  * Every RPC call is tried against each endpoint in order until one answers.

Usage:
  python screen_mint.py 0x870aD5f304871eC0c63BE1e976406e0b095A32CD --v3 0xb99d2C287631326B3994EE80Ec3D851c36396f76 --label PXIO
  python screen_mint.py --watchlist watchlist.json
  python screen_mint.py --watchlist watchlist.json --json   (machine-readable)
"""

import argparse
import json
import sys
import time
from decimal import Decimal

from web3 import Web3

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}
RPCS = [
    "https://bsc.publicnode.com",          # primary (needs Chrome UA)
    "https://bsc-dataseed.binance.org",    # fallback (also serves old receipts)
    "https://bsc-dataseed1.defibit.io",    # 2nd fallback
]

FACTORY = Web3.to_checksum_address("0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73")
WBNB = Web3.to_checksum_address("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
ZERO = "0x0000000000000000000000000000000000000000"

# Dust line: a V2 pool holding less than this much WBNB on the WBNB side is
# not a market anyone can sell into in practice.
DUST_WBNB = Decimal("0.01")

ERC20_ABI = [
    {"name": "name", "outputs": [{"type": "string"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
    {"name": "symbol", "outputs": [{"type": "string"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
    {"name": "decimals", "outputs": [{"type": "uint8"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
    {"name": "totalSupply", "outputs": [{"type": "uint256"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
]
FACTORY_ABI = [
    {"name": "getPair", "outputs": [{"type": "address"}],
     "inputs": [{"type": "address"}, {"type": "address"}],
     "stateMutability": "view", "type": "function"},
]
PAIR_ABI = [
    {"name": "token0", "outputs": [{"type": "address"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
    {"name": "token1", "outputs": [{"type": "address"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
    {"name": "getReserves", "outputs": [{"type": "uint112"}, {"type": "uint112"},
                                         {"type": "uint32"}],
     "inputs": [], "stateMutability": "view", "type": "function"},
]
V3POOL_ABI = [
    {"name": "slot0", "outputs": [{"type": "uint160"}, {"type": "int24"},
                                  {"type": "uint16"}, {"type": "uint16"},
                                  {"type": "uint16"}, {"type": "uint8"},
                                  {"type": "bool"}],
     "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "liquidity", "outputs": [{"type": "uint128"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
    {"name": "token0", "outputs": [{"type": "address"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
    {"name": "token1", "outputs": [{"type": "address"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
]


def connect():
    """Return (w3, rpc_url) for the first endpoint that answers chain_id."""
    last_err = None
    for rpc in RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(
                rpc, request_kwargs={"timeout": 30, "headers": UA}))
            cid = w3.eth.chain_id
            if cid == 56:
                return w3, rpc
            last_err = f"chain_id={cid}, expected 56"
        except Exception as e:  # noqa: BLE001 - try next RPC
            last_err = repr(e)[:160]
    raise RuntimeError(f"no BSC RPC reachable; last error: {last_err}")


def call_all(fn):
    """Run fn(w3) against each RPC in order; return first success.

    fn must take a Web3 instance and return a value. Raises the last error
    if every endpoint fails.
    """
    last_err = None
    for rpc in RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(
                rpc, request_kwargs={"timeout": 30, "headers": UA}))
            if w3.eth.chain_id != 56:
                continue
            return fn(w3)
        except Exception as e:  # noqa: BLE001 - try next RPC
            last_err = e
    raise last_err


def safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - unreadable field, not fatal
        return default


def human(amount_raw, decimals):
    return Decimal(amount_raw) / Decimal(10 ** decimals)


def v3_price(sqrt_price_x96, dec0, dec1):
    """Human price: units of token1 per 1 unit of token0.

    sqrtPriceX96 encodes sqrt(token1/token0) * 2**96 in raw units, so the
    raw ratio must be corrected by 10**(dec0 - dec1) for human units.
    """
    ratio = (Decimal(sqrt_price_x96) / Decimal(2 ** 96)) ** 2
    return ratio * Decimal(10 ** (dec0 - dec1))


def screen_token(address, label=None, v3_pool=None):
    address = Web3.to_checksum_address(address)
    label = label or address
    out = {"label": label, "address": address, "v3_pool": v3_pool,
           "checks": {}, "verdict": "ERROR", "verdict_reason": ""}

    # ---- Check 1: token identity -------------------------------------
    def _identity(w3):
        t = w3.eth.contract(address=address, abi=ERC20_ABI)
        return {
            "name": safe(t.functions.name().call),
            "symbol": safe(t.functions.symbol().call),
            "decimals": safe(t.functions.decimals().call),
            "totalSupply_raw": safe(t.functions.totalSupply().call),
        }

    ident = call_all(_identity)
    dec = ident["decimals"] if isinstance(ident["decimals"], int) else 18
    ts = ident["totalSupply_raw"]
    out["checks"]["identity"] = {
        "name": ident["name"], "symbol": ident["symbol"],
        "decimals": ident["decimals"],
        "totalSupply": (str(human(ts, dec)) if isinstance(ts, int) else None),
    }

    # ---- Check 2: PancakeSwap V2 pair vs WBNB -------------------------
    def _v2(w3):
        f = w3.eth.contract(address=FACTORY, abi=FACTORY_ABI)
        pair = f.functions.getPair(address, WBNB).call()
        if pair == ZERO:
            return {"pair": None}
        p = w3.eth.contract(address=pair, abi=PAIR_ABI)
        t0 = p.functions.token0().call()
        t1 = p.functions.token1().call()
        r0, r1, _ts = p.functions.getReserves().call()
        dec0 = 18 if t0 == WBNB else dec
        dec1 = 18 if t1 == WBNB else dec
        # WBNB-side reserve, whichever side it sits on
        wbnb_res = human(r0, 18) if t0 == WBNB else human(r1, 18)
        tok_res = human(r1, dec) if t0 == WBNB else human(r0, dec)
        return {"pair": pair, "token0": t0, "token1": t1,
                "reserve_token": str(tok_res), "reserve_wbnb": str(wbnb_res),
                "wbnb_reserve": wbnb_res}

    v2 = call_all(_v2)
    out["checks"]["v2"] = {k: v for k, v in v2.items() if k != "wbnb_reserve"}

    # ---- Check 3: PancakeSwap V3 pool (only if an address is given) ---
    # NOTE (live finding, 2026-11-17): this pool's slot0() return has a
    # non-standard 6th word (feeProtocol reads 0x0c800c80, not a clean
    # uint8), so web3.py's strict ABI decoder rejects the whole call with
    # BadFunctionCallOutput / NonEmptyPaddingBytes. Words 0-1
    # (sqrtPriceX96, tick) are clean, so we parse the raw 224-byte return
    # ourselves instead of trusting the ABI decoder.
    v3 = None
    if v3_pool:
        v3_pool = Web3.to_checksum_address(v3_pool)

        def _v3(w3):
            pool = w3.eth.contract(address=v3_pool, abi=V3POOL_ABI)
            sel = w3.keccak(text="slot0()")[:4]
            raw = w3.eth.call({"to": v3_pool, "data": sel})
            if len(raw) != 224:
                raise ValueError(f"slot0() returned {len(raw)} bytes, expected 224")
            sqrt_px = int.from_bytes(raw[0:32], "big")
            tick = int.from_bytes(raw[32:64], "big", signed=True)
            liq = pool.functions.liquidity().call()
            t0 = pool.functions.token0().call()
            t1 = pool.functions.token1().call()

            def _dec(addr):
                if addr == address:
                    return dec
                c = w3.eth.contract(address=addr, abi=ERC20_ABI)
                d = safe(c.functions.decimals().call)
                return d if isinstance(d, int) else 18

            def _sym(addr):
                if addr == address:
                    return ident["symbol"]
                c = w3.eth.contract(address=addr, abi=ERC20_ABI)
                return safe(c.functions.symbol().call) or addr[:10]

            d0, d1 = _dec(t0), _dec(t1)
            s0, s1 = _sym(t0), _sym(t1)
            price_t1_per_t0 = v3_price(sqrt_px, d0, d1)
            return {"pool": v3_pool, "token0": t0, "token1": t1,
                    "token0_symbol": s0, "token1_symbol": s1,
                    "tick": tick, "liquidity_raw": str(liq),
                    "sqrtPriceX96": str(sqrt_px),
                    "price_token1_per_token0": str(price_t1_per_t0),
                    "price_note": f"1 {s0} = {price_t1_per_t0} {s1} "
                                  f"(1 {s1} = {1 / price_t1_per_t0} {s0})"
                                  if price_t1_per_t0 > 0 else "price = 0"}

        v3 = call_all(_v3)
        out["checks"]["v3"] = v3

    # ---- Verdict -------------------------------------------------------
    if v3 and int(v3["liquidity_raw"]) > 0 and Decimal(
            v3["price_token1_per_token0"]) > 0:
        out["verdict"] = "BUYER PROOF"
        out["verdict_reason"] = (
            f"live V3 pool {v3_pool} with liquidity "
            f"{v3['liquidity_raw']} and a computable price "
            f"({v3['price_note']}). A pool exists — this is buyer "
            f"proof, NOT a guaranteed sell price.")
    elif v2.get("pair"):
        if v2["wbnb_reserve"] >= DUST_WBNB:
            out["verdict"] = "BUYER PROOF"
            out["verdict_reason"] = (
                f"live V2 pair {v2['pair']} holding "
                f"{v2['reserve_wbnb']} WBNB + {v2['reserve_token']} "
                f"{ident['symbol'] or 'tokens'}. Non-dust reserves.")
        else:
            out["verdict"] = "DEAD"
            out["verdict_reason"] = (
                f"V2 pair {v2['pair']} exists but holds only "
                f"{v2['reserve_wbnb']} WBNB — dust. No real liquidity.")
    else:
        out["verdict"] = "WATCH"
        out["verdict_reason"] = (
            "no PancakeSwap V2 pair vs WBNB"
            + (f" and no live V3 pool checked" if not v3_pool else
               " and the given V3 pool has no usable liquidity")
            + ". No buyers yet — do not mint for resale.")

    return out


def render(res, rpc):
    lines = []
    c = res["checks"]
    ident = c.get("identity") or {}
    lines.append(f"== {res['label']}  {res['address']}  (via {rpc}) ==")
    if not ident:
        lines.append(f"ERROR: {res.get('verdict_reason', 'check failed')}")
        lines.append(f"VERDICT: {res['verdict']}")
        return "\n".join(lines)
    lines.append(
        f"[1] identity: name={ident['name']!r} symbol={ident['symbol']!r} "
        f"decimals={ident['decimals']} totalSupply={ident['totalSupply']}")
    v2 = c["v2"]
    if v2.get("pair"):
        lines.append(
            f"[2] V2 pair vs WBNB: {v2['pair']} token0={v2['token0']} "
            f"token1={v2['token1']}")
        lines.append(
            f"    reserves: {v2['reserve_token']} {ident['symbol']} + "
            f"{v2['reserve_wbnb']} WBNB")
    else:
        lines.append("[2] V2 pair vs WBNB: NONE (getPair returned 0x000...0)")
    v3 = c.get("v3")
    if v3:
        lines.append(
            f"[3] V3 pool {v3['pool']} ({v3['token0_symbol']}/{v3['token1_symbol']}) "
            f"tick={v3['tick']} liquidity={v3['liquidity_raw']}")
        lines.append(f"    price: {v3['price_note']}")
    elif res.get("v3_pool"):
        lines.append("[3] V3 pool: UNREADABLE (see error above)")
    else:
        lines.append("[3] V3 pool: not given (pass --v3 <pool> to check one)")
    lines.append(f"VERDICT: {res['verdict']} — {res['verdict_reason']}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Free-mint screener (BSC, read-only).")
    ap.add_argument("address", nargs="?", help="BSC token contract address")
    ap.add_argument("--label", help="short name for the token")
    ap.add_argument("--v3", dest="v3_pool", help="PancakeSwap V3 pool address")
    ap.add_argument("--watchlist", help="JSON list of {label, address, v3_pool?}")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)

    targets = []
    if args.watchlist:
        with open(args.watchlist) as f:
            data = json.load(f)
        for item in data:
            targets.append((item["address"], item.get("label"),
                            item.get("v3_pool")))
    elif args.address:
        targets.append((args.address, args.label, args.v3_pool))
    else:
        ap.error("give a token address or --watchlist watchlist.json")

    try:
        _w3, rpc = connect()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    results, stamp = [], time.strftime("%Y-%m-%d %H:%M:%S %Z")
    for addr, label, v3_pool in targets:
        try:
            res = screen_token(addr, label, v3_pool)
        except Exception as e:  # noqa: BLE001 - one bad token must not kill the run
            res = {"label": label or addr, "address": addr,
                   "v3_pool": v3_pool, "checks": {},
                   "verdict": "ERROR", "verdict_reason": f"check failed: {e!r}"}
        results.append(res)
        if not args.json:
            print(render(res, rpc))
            print()

    if args.json:
        print(json.dumps({"run_at": stamp, "rpc": rpc, "results": results},
                         indent=2))
    else:
        counts = {}
        for r in results:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        print("SUMMARY: " + ", ".join(
            f"{k}={v}" for k, v in sorted(counts.items()))
            + f"  (n={len(results)}, {stamp})")
        print("Read-only: no keys, no transactions, no writes. "
              "A paper price is not cash — reserves are buyer proof only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
