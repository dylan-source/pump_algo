import requests

def get_dex_paid(token_address):

    response = requests.get(
        f"https://api.dexscreener.com/orders/v1/solana/{token_address}",
        headers={},
    )
    data = response.json()
    print(data)

    if not data:
        return False
    else:
        return True


get_dex_paid("CXStz3QK8fGygd7ky6NrrU3ZfcJpwAKTvpBySawspump")  
