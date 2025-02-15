import json
import asyncio
import requests

WSOL = "So11111111111111111111111111111111111111112"

def get_pool_info_by_id(pool_id: str) -> dict:
    base_url = "https://api-v3.raydium.io/pools/info/ids"
    params = {"ids": pool_id}
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch pool info: {e}"}

async def get_pool_info_by_mint(mint: str, pool_type: str = "all", sort_field: str = "default", 
                              sort_type: str = "desc", page_size: int = 100, page: int = 1) -> dict:
    base_url = "https://api-v3.raydium.io/pools/info/mint"
    params = {
        "mint1": mint,
        "poolType": pool_type,
        "poolSortField": sort_field,
        "sortType": sort_type,
        "pageSize": page_size,
        "page": page
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        response = response.json() 
    
        # Return False is call fails
        if not response.get('success', False):
            return False
    
        # Extract data list
        data_list = response.get('data', {}).get('data', [])
        
        # Iterate over data and check for the condition
        for item in data_list:
            mintA_address = item.get('mintA', {}).get('address', '')
            mintB_address = item.get('mintB', {}).get('address', '')
            
            # Check if either mintA or mintB has the specified address
            if mintA_address == WSOL or mintB_address == WSOL:
                return item.get('id', None)

        return None  # Return None if no match is found
    
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch pair address: {e}"}


# if __name__ == "__main__":
#     result = asyncio.run(get_pool_info_by_mint("45CPLcWGGzVv8Adb7P4G1XMJiagrcDjKNN79hFXLpump"))
#     print(json.dumps(result, indent=4))