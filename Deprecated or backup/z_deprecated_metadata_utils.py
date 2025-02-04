# metadata_utils.py
from config import RPC_URL, METADATA_PROGRAM_ID, logger
from solders.pubkey import Pubkey # type: ignore
from io import BytesIO

async def fetch_token_metadata(httpx_client, token_mint):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAsset",
        "params": {"id": token_mint}
    }
    
    response = await httpx_client.post(url=RPC_URL, headers={'Content-Type':'application/json'}, json=payload)
    data = response.json()
    data = data["result"]["content"]["metadata"]
    return data["name"], data["symbol"]


async def fetch_token_metadata_metaplex(async_client, token_mint):
    try:
        metadata_account = await get_metadata_account(token_mint)

        # Request with encoding="base64" or try without specifying encoding if this doesn't work
        response = await async_client.get_account_info(metadata_account, commitment="finalized", encoding="base64")

        account_info = response.value
        if account_info is None:
            logger.warning(f"Metadata account not found for token mint: {token_mint}")
            return None, None

        # Get raw bytes and parse
        decoded_data = account_info.data 
        metadata = parse_metadata_account(decoded_data)

        token_name = metadata['name']
        token_symbol = metadata['symbol']
        return token_symbol, token_name
    except Exception as e:
        logger.error(f"Error fetching token metadata: {e}")
        return None, None


# Get the public key from Metaplex
async def get_metadata_account(token_mint):
    seeds = [
        b"metadata",
        bytes(METADATA_PROGRAM_ID),
        bytes(Pubkey.from_string(token_mint))
    ]
    metadata_pubkey, _ = Pubkey.find_program_address(seeds, METADATA_PROGRAM_ID)
    return metadata_pubkey


# Parse the metadata and extract the relevant data points
def parse_metadata_account(data):
    try:
        stream = BytesIO(data)
        name_length = int.from_bytes(stream.read(4), 'little')
        name = stream.read(name_length).decode('utf-8')
        symbol_length = int.from_bytes(stream.read(4), 'little')
        symbol = stream.read(symbol_length).decode('utf-8')
        # Reading and parsing fields
        # key = int.from_bytes(stream.read(1), 'little')
        # update_authority = stream.read(32)
        # mint = stream.read(32)
        # uri_length = int.from_bytes(stream.read(4), 'little')
        # uri = stream.read(uri_length).decode('utf-8')
        # seller_fee_basis_points = int.from_bytes(stream.read(2), 'little')
        # primary_sale_happened = bool(int.from_bytes(stream.read(1), 'little'))
        # is_mutable = bool(int.from_bytes(stream.read(1), 'little'))

        name = name.strip()
        symbol = symbol.strip()

        return {'name': name, 'symbol': symbol}
    except Exception as e:
        logger.error(f"Error parsing metadata account: {e}")
        return {'name': None, 'symbol': None}
