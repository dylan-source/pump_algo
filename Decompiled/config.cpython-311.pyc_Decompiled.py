# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: /Users/dylanmartens/Documents/Coding/Pump sniping/Feb_03/config.py
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2025-02-03 16:12:57 UTC (1738599177)

import os
import sys
import logging
import base58
from dotenv import load_dotenv, find_dotenv, dotenv_values
from solders.pubkey import Pubkey
from solders.keypair import Keypair
load_dotenv()
WS_URL = os.getenv('WS_URL', '')
RPC_URL = os.getenv('RPC_URL', '')
METIS_RPC_URL = os.getenv('METIS_RPC_URL', '')
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS', '')
COLD_WALLET_ADDRESS = os.getenv('COLD_WALLET_ADDRESS', '')
SIGNATURE = os.getenv('RUGCHECK_SIGNATURE')
TWEET_SCOUT_KEY = os.getenv('TWEET_SCOUT_API_KEY')
CSV_MIGRATIONS_FILE = 'migration_data.csv'
CSV_TRADES_FILE = 'trade_data.csv'
PRIVATE_KEY_RAW = os.getenv('PRIVATE_KEY', '')
PRIVATE_KEY = Keypair.from_bytes(base58.b58decode(PRIVATE_KEY_RAW))
STOPLOSS = 0.25
COMMITTMENT_LEVEL = 'finalized'
RELAY_DELAY = 15
TIME_TO_SLEEP = 15
TIMEOUT = 30000
HTTPX_TIMEOUT = 10
MAX_TRADE_TIME_MINS = 8
SELL_LOOP_DELAY = 10
MONITOR_PRICE_DELAY = 2
PRICE_LOOP_RETRIES = 5
START_UP_SLEEP = 10
SOL_DECIMALS = 9
TRADE_AMOUNT_SOL = 0.0001
SOL_AMOUNT_LAMPORTS = int(TRADE_AMOUNT_SOL * 10 ** SOL_DECIMALS)
MIN_SOL_BALANCE = 0.1
SOL_MIN_BALANCE_LAMPORTS = int(MIN_SOL_BALANCE * 10 ** SOL_DECIMALS)
SOL_MINT = 'So11111111111111111111111111111111111111112'
PRIORITY_FEE_NUM_BLOCKS = 150
PRIORITY_FEE_MULTIPLIER = 1.2
PRIORITY_FEE_MIN = 30000
PRIORITY_FEE_MAX = 1000000
BUY_SLIPPAGE = {'MIN': 2000, 'MAX': 3000, 'INCREMENTS': 500}
SELL_SLIPPAGE = {'MIN': 2000, 'MAX': 4000, 'INCREMENTS': 500}
JUPITER_QUOTE_URL = 'https://api.jup.ag/swap/v1/quote'
JUPITER_SWAP_URL = 'https://api.jup.ag/swap/v1/swap'
JUPITER_PRICE_URL = 'https://api.jup.ag/price/v2'
MIGRATION_ADDRESS = '39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg'
METADATA_PROGRAM_ID = Pubkey.from_string('metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s')
JUPITER_V6_ADDRESS = 'JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4'

class ColoredFormatter(logging.Formatter):
    RED = '\x1b[91m'
    RESET = '\x1b[0m'

    def format(self, record):
        message = super().format(record)
        if record.levelno >= logging.ERROR:
            message = f'{self.RED}0{message}0{self.RESET}0'
        return message
plain_formatter = logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
colored_formatter = ColoredFormatter(fmt='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
migrations_logger = logging.getLogger('migrations_logger')
migrations_logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(colored_formatter)
migrations_logger.addHandler(console_handler)
migrations_file_handler = logging.FileHandler('migrations.log')
migrations_file_handler.setLevel(logging.INFO)
migrations_file_handler.setFormatter(plain_formatter)
migrations_logger.addHandler(migrations_file_handler)
trade_logger = logging.getLogger('trade_logger')
trade_logger.setLevel(logging.INFO)
trade_file_handler = logging.FileHandler('trade.log')
trade_file_handler.setLevel(logging.INFO)
trade_file_handler.setFormatter(plain_formatter)
trade_logger.addHandler(trade_file_handler)
trade_console_handler = logging.StreamHandler(sys.stdout)
trade_console_handler.setLevel(logging.INFO)
trade_console_handler.setFormatter(colored_formatter)
trade_logger.addHandler(trade_console_handler)
httpx_logger = logging.getLogger('httpx')
httpx_logger.setLevel(logging.WARNING)
httpcore_logger = logging.getLogger('httpcore')
httpcore_logger.setLevel(logging.WARNING)