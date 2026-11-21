# Free-Mint Screener — zkVerify Agent Games, Wildcard Track

A small, real, read-only screener for BNB Chain that answers one question
**before** you spend gas on a "free" mint: **is there anyone to sell to?**

## The problem

Most "free" Agent ID token/NFT mints on BNB Chain have no buyers. The mint
itself costs gas, and the tokens it produces can never be sold — there is no
pool, no order book, no bid. People mint them anyway because the mint page
says "free" and shows a hopeful price. This screener checks for buyer proof
**on-chain, before minting**, so gas is only spent where a market exists.

## How it works — the 3 checks

`screen_mint.py` (Python, web3.py 8.0.0, read-only: no private keys, no
transactions, no chain writes) runs three on-chain checks per token:

1. **Identity** — `name()` / `symbol()` / `decimals()` / `totalSupply()`.
   Confirms the address is a real token and reports its supply.
2. **PancakeSwap V2 pool** — `factory.getPair(token, WBNB)` on the V2
   factory (`0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73`). If it returns
   `0x000…0`, there is no pool. If a pair exists, `token0()` / `token1()` /
   `getReserves()` report the human-readable reserves on both sides.
3. **PancakeSwap V3 pool** — for a given pool address, `slot0()` +
   `liquidity()`, with price math
   `price = (sqrtPriceX96 / 2^96)^2`, adjusted for decimals and token0/token1
   order, so the output reads `1 USDT = 9,950.6 PXIO`.

### Verdicts

| Verdict | Meaning |
|---|---|
| `BUYER PROOF` | A live pool with non-dust liquidity exists. Someone *can* buy. |
| `WATCH` | No pool yet — nothing to sell into. Do not mint for resale. |
| `DEAD` | A pool exists but reserves are dust (< 0.01 WBNB on the WBNB side). No real liquidity. |

A paper price is **never** presented as cashable money. Reserves are a proxy
for "a buyer could exist", not a tested sell route.

### Bonus: NFT mode

`nft_check.py` applies the same rule to Element listings via the already
verified Element GraphQL helper (`floor_for()` in
`~/workspace/goals/sellable-nft-sale/hidden_files/el_floors.py`): a
collection with `totalVolume > 0` has provably sold before; a floor with
`totalVolume == 0` is only the cheapest ask — nobody has paid it.

### How the watchlist token addresses were found

WOJAGENT / WNO / NEBULA had no published token address. `derive_tokens.py`
reads each mint tx's receipt and takes the token contract from the ERC-20
`Transfer` event delivered to the user's wallet
(`0xFc194660992b41f6A3B395BeEceAa8C219c37937`):

- WOJAGENT → `0x62EC413381B74387b57F1E2734cdd2E5b96a57B7` (41,175,000 delivered)
- WNO → `0x8C969a4CD49E4774908e667702C3d7C3ece164D0` (1,000,000 delivered)
- NEBULA → `0xF08aC9C91dCfC5B74eAE6c87E744CfEFE0d32A68` (1,000 delivered)

## How to run

```bash
cd ~/workspace/zkverify-agent-games/wildcard
~/workspace/.venv-web3/bin/python derive_tokens.py
~/workspace/.venv-web3/bin/python screen_mint.py --watchlist watchlist.json
~/workspace/.venv-web3/bin/python screen_mint.py 0x870aD5f304871eC0c63BE1e976406e0b095A32CD --v3 0xb99d2C287631326B3994EE80Ec3D851c36396f76 --label PXIO
~/workspace/.venv-web3/bin/python screen_mint.py --watchlist watchlist.json --json   # machine-readable
~/workspace/.venv-web3/bin/python nft_check.py --holdings nft_holdings.json
```

Requirements: the venv at `~/workspace/.venv-web3` (web3 8.0.0, PIL).
No API keys, no wallet, no login. Full watchlist run takes ~2–3 minutes
(public RPC latency).

## Live results — run 2026-11-17 23:55–23:57 WIB (16:55–16:57 UTC)

Full verbatim output: [`run-log-2026-11-17.txt`](run-log-2026-11-17.txt).
Screenshot rendered from that log: [`screenshot.png`](screenshot.png).

### Tokens (`screen_mint.py --watchlist watchlist.json`)

| Token | Identity (on-chain) | V2 pair vs WBNB | V3 pool | Verdict |
|---|---|---|---|---|
| PXIO `0x870a…32CD` | PXIO, 18 dec, supply 1,000,000,000 | none | `0xb99d…f76` USDT/PXIO, tick 92058, liquidity 5,002,002,504,091,440,580,465,291; **1 USDT = 9,950.61 PXIO (1 PXIO = 0.0001004964 USDT)** | **BUYER PROOF** |
| AMNT `0x2d07…e4E` | Agent Mining, 8 dec, supply 1,348,665,000 | none | — | WATCH |
| OVF `0xB369…e6C` | OVREK, 18 dec, supply 50,000,000,000 | none | — | WATCH |
| CTX `0x9E1A…b88` | Contextgraph, 18 dec, supply 10,000,000,000 | none | — | WATCH |
| WOJAGENT `0x62EC…57B7` | Wojak Agent, 18 dec, supply 1,000,000,000,000 | none | — | WATCH |
| WNO `0x8C96…64D0` | War Need Over, 18 dec, supply 6,000,000,000 | none | — | WATCH |
| NEBULA `0xF08a…32A68` | NEBULA (NEB), 18 dec, supply 3,936,600 | none | — | WATCH |

Summary: **BUYER PROOF = 1, WATCH = 6 (n = 7).** Only PXIO has a market.
The other six are exactly the trap this screener exists for: free to mint,
impossible to sell. (AMNT's earlier "$0.000031 paper quote" was never a
cashable price — no pool, no route — and this run confirms it again.)

Note the price moved between two live runs minutes apart (9,950.59 →
9,950.61 PXIO per USDT): the pool is genuinely live, and the numbers above
are a snapshot, not a quote.

### NFTs (`nft_check.py --holdings nft_holdings.json`)

| Collection | Floor (BNB) | Total volume (BNB) | Verdict |
|---|---|---|---|
| Wise Owl Society (`wise-owl-society`, 4,168 items) | 0.00031 (~$0.18) | 0.019595 | **SOLD BEFORE** |
| Claf Eye (`claf`, 7,207 items) | 0.0001188 (~$0.069) | 0.0 | LISTED, NEVER SOLD |
| Ovrek Foundry Faces (`foundry-faces`, 2,187 items) | 0.0015 (~$0.88) | 0.0 | LISTED, NEVER SOLD |
| Sidecoo Agent Pass (`sidecoo-agent-pass`, 9,819 items) | 0.00000698 (~$0.004) | 0.0 | LISTED, NEVER SOLD |

Summary: **SOLD BEFORE = 1, LISTED, NEVER SOLD = 3 (n = 4).** Three of the
four "listed" collections have never had a single sale — their floors are
asks, not prices.

## Honest limitations

- **Reserves are a proxy, not a sale.** This screener proves a pool exists
  and holds liquidity; it does not execute a test swap, so slippage, taxes,
  honeypot behaviour, or a broken sell path would not show up here.
- **24h volume needs an indexer.** On-chain reserves say nothing about how
  much traded yesterday. Volume would come from a subgraph/indexer, which
  this demo does not run.
- **V3 price needs tick math.** The price above comes from `sqrtPriceX96`
  (cross-checked against `tick = 92058`, which implies the same ~9,950
  PXIO/USDT). Concentrated-liquidity depth at a given size is not computed.
- **V3 `liquidity` is raw units, not USD.** The reported
  `5,002,002,504,091,440,580,465,291` is the pool's active liquidity in
  sqrt-price units; converting it to a dollar depth needs the tick range of
  the positions, which is out of scope.
- **Only the pools named in the watchlist are checked.** A token could have
  a V3 pool this run never looked at (none of the six WATCH tokens has a V2
  pair, which is the cheap first filter; a V3-only pool elsewhere would be
  missed unless its address is added with `--v3`).
- **AMNT / OVF / CTX / WOJAGENT / WNO / NEBULA verdicts are "no pool found
  on the checked venues",** not a proof that no buyer exists anywhere.

## Gotchas found while building (all live, 2026-11-17)

- `web3.py` `get_block()` **fails on BSC** (POA `extraData`) — this code
  never calls it; only `eth_call` / `eth_getTransactionReceipt`.
- `bsc.publicnode.com` returns **HTTP 403** to web3's default User-Agent and
  rejects `eth_getTransactionReceipt` for old blocks as an "archive request"
  (needs a personal token). Fix: send a Chrome User-Agent, and fall back to
  `bsc-dataseed.binance.org` (which serves old receipts fine). Every RPC
  call in `screen_mint.py` tries each endpoint in order until one answers.
- The PXIO V3 pool's `slot0()` return has a **non-standard 6th word**
  (`feeProtocol` reads `0x0c800c80`, not a clean uint8), so web3.py's strict
  ABI decoder rejects the whole call (`BadFunctionCallOutput` /
  `NonEmptyPaddingBytes`). Words 0–1 (`sqrtPriceX96`, `tick`) are clean, so
  `screen_mint.py` parses the raw 224-byte return itself.
- Element's saved API key was rejected by Element long ago and is never
  retried; the NFT check uses the site's public GraphQL key + HMAC from the
  already-verified helper instead.

## Files

- `screen_mint.py` — the screener (3 checks, verdicts, `--watchlist` / `--json`)
- `watchlist.json` — 7 candidate tokens (3 addresses derived from mint receipts)
- `derive_tokens.py` — derives token contracts from mint-tx receipts
- `nft_check.py` + `nft_holdings.json` — optional NFT floor/volume mode
- `run-log-2026-11-17.txt` — verbatim terminal output of the live run
- `screenshot.png` — the log rendered as a terminal screenshot (PIL)
- `README.md` — this file

Read-only demo: no private keys, no transactions, no logins, no posting,
nothing submitted anywhere.
