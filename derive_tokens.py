#!/usr/bin/env python3
"""Derive ERC-20 token contract addresses from free-mint tx receipts.

A mint tx's receipt logs contain the ERC-20 Transfer event; the log's
`address` field IS the token contract, and the Transfer to the user's wallet
confirms which token was actually delivered. This is how the WOJAGENT / WNO /
NEBULA entries in watchlist.json were found — read from the chain, not guessed.

Gotcha (live, 2026-11-17): bsc.publicnode.com rejects eth_getTransactionReceipt
for old blocks ("Archive requests require a personal token"), so receipts are
fetched from bsc-dataseed.binance.org. Read-only; no keys, no transactions.
"""
import json
import sys
from web3 import Web3

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
TRANSFER_TOPIC = "ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
USER = "0xFc194660992b41f6A3B395BeEceAa8C219c37937"

TXS = {
    "WOJAGENT": "0x0a35deb24d0ddc7b8ad40b7e1d200964d0b82008858b2a16d87bce921acbd04e",
    "WNO": "0x76cdfb68142a2fb8cef7b2137f417b9954b63ce569c4831490b3d4960a2d8691",
    "NEBULA": "0xaf82e2567c1151f12cabfb545011e7a35a767da23cefd18919befc6ddd90f232",
}


def main():
    w3 = Web3(Web3.HTTPProvider("https://bsc-dataseed.binance.org",
                                request_kwargs={"timeout": 30, "headers": UA}))
    print(f"chain_id={w3.eth.chain_id} via bsc-dataseed.binance.org")
    found = {}
    for name, txh in TXS.items():
        r = w3.eth.get_transaction_receipt(txh)
        print(f"\n{name} mint tx {txh} status={r['status']} block={r['blockNumber']}")
        for log in r["logs"]:
            topics = [t.hex() for t in log["topics"]]
            if topics and topics[0] == TRANSFER_TOPIC and len(topics) >= 3:
                to = "0x" + topics[2][-40:]
                amt = int(log["data"].hex(), 16)
                if to.lower() == USER.lower():
                    token = Web3.to_checksum_address(log["address"])
                    found[name] = token
                    print(f"  Transfer -> user: token={token} amount_raw={amt}")
    print("\nDerived token contracts:")
    print(json.dumps(found, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
