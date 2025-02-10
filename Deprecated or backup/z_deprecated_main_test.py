import httpx
import asyncio
from config import RPC_URL


def fetch_token_metadata(token_mint):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAsset",
        "params": {"id": token_mint}
    }
    
    response = httpx.post(url=RPC_URL, headers={'Content-Type':'application/json'}, json=payload)
    data = response.json()
    print(data)
    data = data["result"]["content"]["metadata"]
    return data["name"], data["symbol"]

if __name__ == "__main__":
    
    token_mint = "ESLvBNKz2SHAW9GFh3Fbu6uaQuvvCrhSvMiK67mWpump"
    fetch_token_metadata(token_mint)


                      