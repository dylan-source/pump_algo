from solana.rpc.api import Client
from solders.keypair import Keypair #type: ignore

PRIV_KEY = "45uo4dRrPYJwKyxmDQ1Py4NihBSPVxYgDmK36cxeybAoZ57M7o9R4kNrn5vWyiaHZ4mxqvXfNsJDBDyH1A1jyXQ1"
RPC = "https://wild-shy-daylight.solana-mainnet.quiknode.pro/d238b8c7629e3c71f5605e7bb89d93a8db815160"
UNIT_BUDGET =  150_000
UNIT_PRICE =  1_000_000
client = Client(RPC)
payer_keypair = Keypair.from_base58_string(PRIV_KEY)