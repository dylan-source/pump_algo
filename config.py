import os
import sys
import getpass
import logging
import base58
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from solders.pubkey import Pubkey     # type: ignore
from solders.keypair import Keypair   # type: ignore

from solana.rpc.async_api import AsyncClient

load_dotenv()

# Load remaining environment varialbes
WS_URL = os.getenv('WS_URL', '')
RPC_URL = os.getenv('RPC_URL', '')
METIS_RPC_URL = os.getenv('METIS_RPC_URL', '')
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS', '')
COLD_WALLET_ADDRESS = os.getenv('COLD_WALLET_ADDRESS', '')
SIGNATURE = os.getenv('RUGCHECK_SIGNATURE')
TWEET_SCOUT_KEY = os.getenv('TWEET_SCOUT_API_KEY')

# Define the CSVs to save files
CSV_MIGRATIONS_FILE = 'migration_data.csv'
CSV_TRADES_FILE = 'trade_data.csv'

# Define trading parameters
STOPLOSS = 0.10                     # trailing stoploss value
COMMITTMENT_LEVEL = 'finalized'     # level at which sol processing occurs
RELAY_DELAY = 15                    # time when to reconnect to websocket after it drops
TIME_TO_SLEEP = 15                  # sleep time between api calls for filters_utils functions
TIMEOUT = 30000                     # sleep time between api calls for filters_utils functions -> mainly for scraping functions
HTTPX_TIMEOUT = 10                  # timeout specifically for HTTPX
MAX_TRADE_TIME_MINS = 5             # maximum trade duration
SELL_LOOP_DELAY = 10                # delay between api calls in execute_sell function
MONITOR_PRICE_DELAY = 3             # length of time between price API calls -> to prevent rate limit
PRICE_LOOP_RETRIES = 5              # max number of times to attempt to fetch a rpice
START_UP_SLEEP = 5                  # number of seconds after migration before attempting to buy -> often an error occurs if too soon

# Define SOL constants
SOL_DECIMALS = 9
TRADE_AMOUNT_SOL = 0.001
SOL_AMOUNT_LAMPORTS = int(TRADE_AMOUNT_SOL * 10 ** SOL_DECIMALS)
MIN_SOL_BALANCE = 0.1
SOL_MIN_BALANCE_LAMPORTS = int(MIN_SOL_BALANCE * 10 ** SOL_DECIMALS)
SOL_MINT = 'So11111111111111111111111111111111111111112'

# Define priority fee ranges
PRIORITY_FEE_MIN=50_000
PRIORITY_FEE_MAX=250_000
PRIORITY_FEE_NUM_BLOCKS=100
PRIORITY_FEE_MULTIPLIER=1.1
PRIORITY_FEE_STOPLOSS_MULTIPLIER=1.5
PRIORITY_FEE_DICT = {
    "PRIORITY_FEE_MIN": 50_000,
    "PRIORITY_FEE_MAX": 250_000,
    "PRIORITY_FEE_NUM_BLOCKS": 100,
    "PRIORITY_FEE_MULTIPLIER": 1.1,
    "PRIORITY_FEE_STOPLOSS_MULTIPLIER": 1.5
}

# Define slippage dictionaries
BUY_SLIPPAGE = {'MIN': 5, 'MAX': 20, 'INCREMENTS': 5}
SELL_SLIPPAGE = {'MIN': 0, 'MAX': 30, 'INCREMENTS': 5, 'STOPLOSS_MIN': 20}
SELL_SLIPPAGE_DELAY = 5 

# Load the Jupiter URLs
JUPITER_QUOTE_URL = "https://public.jupiterapi.com/quote"   # Direct URL: 'https://api.jup.ag/swap/v1/quote'
JUPITER_SWAP_URL = 'https://api.jup.ag/swap/v1/swap'
JUPITER_PRICE_URL = 'https://api.jup.ag/price/v2'

# Load the relevant addresses
MIGRATION_ADDRESS = '39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg'
METADATA_PROGRAM_ID = Pubkey.from_string('metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s')
JUPITER_V6_ADDRESS = 'JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4'
RAYDIUM_ADDRESS = '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8'   

#----------------------
#   DEFINE LOGGER
#----------------------

# Create a class to colour the logger for the console
class ColoredFormatter(logging.Formatter):
    RED = '\x1b[91m'
    RESET = '\x1b[0m'

    def format(self, record):
        message = super().format(record)
        if record.levelno >= logging.ERROR:
            message = f'{self.RED}{message}{self.RESET}'
        return message

# Define the logger formats
plain_formatter = logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
colored_formatter = ColoredFormatter(fmt='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Define the migration logger
migrations_logger = logging.getLogger('migrations_logger')
migrations_logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(colored_formatter)
migrations_logger.addHandler(console_handler)

# Define the migrations file logger
migrations_file_handler = logging.FileHandler('migrations.log')
migrations_file_handler.setLevel(logging.INFO)
migrations_file_handler.setFormatter(plain_formatter)
migrations_logger.addHandler(migrations_file_handler)

# Define the trade file logger
trade_logger = logging.getLogger('trade_logger')
trade_logger.setLevel(logging.INFO)
trade_file_handler = logging.FileHandler('trade.log')
trade_file_handler.setLevel(logging.INFO)
trade_file_handler.setFormatter(plain_formatter)
trade_logger.addHandler(trade_file_handler)

# Define the trade console logger
trade_console_handler = logging.StreamHandler(sys.stdout)
trade_console_handler.setLevel(logging.INFO)
trade_console_handler.setFormatter(colored_formatter)
trade_logger.addHandler(trade_console_handler)

# Downgrade the HTTPx logger (very verbose by default)
httpx_logger = logging.getLogger('httpx')
httpx_logger.setLevel(logging.WARNING)
httpcore_logger = logging.getLogger('httpcore')
httpcore_logger.setLevel(logging.WARNING)


#---------------------------
#     DECRYPT PRIVATE KEY
#---------------------------

# Retrieve the encrypted private key from your .env file.
encrypted_private_key = os.getenv("ENCRYPTED_PRIVATE_KEY")
if not encrypted_private_key:
    raise Exception("ENCRYPTED_PRIVATE_KEY not set in .env.")

# Attempt to retrieve the master encryption key from an environment variable.
encryption_key = getpass.getpass("Enter your master encryption key: ")
if not encryption_key:
    raise Exception("Master encryption key is required.")

# Decrypt the private key using the master encryption key.
cipher = Fernet(encryption_key.encode())
decrypted_private_key = cipher.decrypt(encrypted_private_key.encode()).decode()

# Convert the decrypted base58-encoded private key into bytes and load it into Keypair.
PRIVATE_KEY = Keypair.from_bytes(base58.b58decode(decrypted_private_key))

# At this point, PRIVATE_KEY is ready to be used with solana.py.
trade_logger.info("Private key successfully decrypted and loaded.")


#-----------------------------
#     RAYDIUM_PY CONFIGS
#-----------------------------

UNIT_BUDGET =  150_000      # max compute units to use - seems to average about 65k typically
# UNIT_PRICE =  500_000       # priority fee per computer unit to use
client = AsyncClient(RPC_URL)
payer_keypair = PRIVATE_KEY




