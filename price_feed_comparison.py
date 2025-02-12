
import requests
import httpx
from httpx._config import Timeout
import asyncio
from solana.rpc.async_api import AsyncClient
from config import (RPC_URL, JUPITER_PRICE_URL, trade_logger, MONITOR_PRICE_DELAY, PRICE_LOOP_RETRIES,)

'''
    Code to test different price feeds - Codex.io is the best (ito accuracy and speed)
'''



# Fetch token price from Jupiter
async def get_jupiter_price(client: httpx.AsyncClient, address: str, timeout: int = 10):
    payload = {
        "ids": address,
        # Do not use vsToken as we want prices in USDC.
        "showExtraInfo": False
    }

    loop_count = 0
    while True:
        try:
            response = await client.get(url=JUPITER_PRICE_URL, params=payload, timeout=Timeout(timeout=timeout))
            response_json = response.json()
        except Exception as e:
            trade_logger.error(f"Error fetching price for {address}: {e}")
            return None

        # Check if the token data exists in the response
        token_data = response_json.get("data", {}).get(address)
        if token_data is None:
            # Sometimes no prices are available yet; return None (or consider a retry)
            return None

        # First, try to get the last traded price
        last_traded_price = token_data.get("lastTradedPrice")
        if last_traded_price is not None:
            return float(last_traded_price)

        # Fall back to the derived price if no last traded price is available
        derived_price = token_data.get("price")
        if derived_price is not None:
            return float(derived_price)

        # Neither price is available; log error and retry up to the maximum retries
        trade_logger.error(f"No price received for {address}")
        loop_count += 1
        if loop_count > PRICE_LOOP_RETRIES:
            return None
        await asyncio.sleep(MONITOR_PRICE_DELAY)



async def get_price_dexscreener(httpx_client:httpx.AsyncClient, token_address:str, chain_id:str="solana") -> float:
    """
    Fetch the priceNative value from the DexScreener token-pairs API for the given chain and token.
    Returns: float: The priceNative (price relative to SOL) value as a float, or None if an error occurs.
    """
    url = f"https://api.dexscreener.com/token-pairs/v1/{chain_id}/{token_address}"
    try:
        response = await httpx_client.get(url)
        response.raise_for_status()  # Raises an error for 4xx/5xx responses.
        data = response.json()

        # Check that the data is a non-empty list.
        if isinstance(data, list) and len(data) > 0:
            first_pair = data[0]
            if "priceNative" in first_pair:
                # price_native_str = first_pair["priceNative"]
                user_price = first_pair["priceUsd"]
                return float(user_price)
            else:
                trade_logger.error("Could not find 'priceNative' in the first pair object.")
                return None
        else:
            trade_logger.error("Response JSON is not a non-empty list.")
            return None

    except httpx.HTTPStatusError as e:
        trade_logger.error(f"HTTP error while fetching priceNative: {e} - Response: {e.response.text}")
    except Exception as e:
        trade_logger.error(f"Unexpected error fetching priceNative: {e}")
    
    return None



codex_api_key = ""
def get_codex_price(client: httpx.AsyncClient, address: str, timeout: int = 10):

    CODEX_PRICE_URL = "https://graph.codex.io/graphql"
    headers = {"content_type":"application/json", "Authorization": codex_api_key}
    params = {"addresses": address, "networkId": 1399811149}

    get_prices = """{
                    getTokenPrices(
                        inputs: [
                        { address: "5wKGBeVWfHhGDp7qTjnQGMopmzVgeK94BTBD4RQYpump", networkId: 1399811149 }
                        ]
                    ) {
                        address
                        networkId
                        priceUsd
                    }
                    }"""

    response = requests.post(CODEX_PRICE_URL, headers=headers, json={"query": get_prices})
    price = response.json()
    return price["data"]["getTokenPrices"][0]["priceUsd"]


    # loop_count = 0
    # while True:
    #     try:
    #         response = await client.get(
    #             url=CODEX_PRICE_URL,
    #             headers=headers,
    #             params=params,
    #             timeout=Timeout(timeout=timeout)
    #         )
    #         response_json = response.json()
    #     except Exception as e:
    #         trade_logger.error(f"Error fetching Codex price for {address}: {e}")
    #         return None

    #     # The Codex.io response is expected to include a "data" field with a list of token objects.
    #     data_list = response_json.get("data", [])
    #     if not data_list:
    #         # No data returned for the given address.
    #         return None

    #     # Find the token data that matches the provided address.
    #     token_data = next(
    #         (item for item in data_list if item.get("tokenAddress", "").lower() == address.lower()),
    #         None
    #     )
    #     if token_data is None:
    #         trade_logger.error(f"No token data found for {address} in Codex.io response")
    #         return None

    #     # Use lastTradedPrice if available; otherwise, use the derived price.
    #     last_traded_price = token_data.get("lastTradedPrice")
    #     if last_traded_price is not None:
    #         return float(last_traded_price)

    #     derived_price = token_data.get("price")
    #     if derived_price is not None:
    #         return float(derived_price)

    #     trade_logger.error(f"No price available for {address} from Codex.io")
    #     loop_count += 1
    #     if loop_count > PRICE_LOOP_RETRIES:
    #         return None
    #     await asyncio.sleep(MONITOR_PRICE_DELAY)



rpc_client = AsyncClient(RPC_URL)
httpx_client = httpx.AsyncClient()


async def main():
    token = "5wKGBeVWfHhGDp7qTjnQGMopmzVgeK94BTBD4RQYpump"
    jupiter_price = await get_jupiter_price(client=httpx_client, address=token)
    dexscreener_price = await get_price_dexscreener(httpx_client=httpx_client, token_address=token)
    codex_price = get_codex_price(client=httpx_client, address=token)
    print(f"Jupiter price: {jupiter_price} - Dexscreener price: {dexscreener_price} - Codex price: {codex_price}")

if __name__ == "__main__":
    asyncio.run(main())


