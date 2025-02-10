# transaction_utils.py
from base64 import b64decode
from construct import Struct, Int8ul
from config import MONITORED_ADDRESS, logger

def extract_token_and_pair_from_response(api_response):
    try:
        # Validate that 'result' exists in the response
        result = api_response.get("result")
        if not result:
            logger.error(f"'result' key missing in API response: {api_response}")
            return None, None

        # Extract transaction details
        transaction = result.get("transaction", {})
        if not transaction:
            logger.error(f"'transaction' key missing in 'result': {result}")
            return None, None

        message = transaction.get("message", {})
        instructions = message.get("instructions", [])
        if not instructions:
            logger.error(f"'instructions' key missing or empty in 'message': {message}")
            return None, None

        # Initialize flags and variables
        account_created = False
        account_initialized = False
        raydium_interaction = False
        account_closed = False

        token_address = None
        pair_address = None

        # Process each instruction
        for instruction in instructions:
            if 'parsed' in instruction:
                program_id = instruction.get('programId')
                parsed = instruction.get('parsed', {})
                info = parsed.get('info', {})
                type_ = parsed.get('type')

                # System Program
                if program_id == '11111111111111111111111111111111':
                    if type_ == 'createAccountWithSeed' and info.get('base') == MONITORED_ADDRESS:
                        account_created = True
                        continue

                # SPL Token Program
                elif program_id == 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA':
                    if type_ == 'initializeAccount' and info.get('owner') == MONITORED_ADDRESS:
                        account_initialized = True
                        continue
                    elif type_ == 'closeAccount' and info.get('destination') == MONITORED_ADDRESS:
                        account_closed = True
                        continue
            else:
                program_id = instruction.get('programId')
                if program_id == '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8':  # Raydium Program
                    raydium_interaction = True
                    accounts = instruction.get('accounts', [])
                    if len(accounts) > 9:
                        token_address = accounts[9]
                    if len(accounts) > 4:
                        pair_address = accounts[4]
                    continue

        # Return the extracted addresses if all conditions are met
        if account_created and account_initialized and raydium_interaction and account_closed:
            logger.info(f"Extracted token: {token_address}, pair: {pair_address}")
            return token_address, pair_address
        else:
            # logger.error(f"Conditions not met: created={account_created}, initialized={account_initialized}, "
            #              f"raydium={raydium_interaction}, closed={account_closed}")
            return None, None
    except Exception as e:
        logger.error(f"Error while parsing the response: {e}")
        logger.debug(f"Raw API response: {api_response}")
        return None, None



def transaction_contains_initialize2(api_response):
    try:
        transaction = api_response.get("transaction", {})
        message = transaction.get("message", {})
        instructions = message.get("instructions", [])

        for instruction in instructions:
            if MONITORED_ADDRESS in instruction.get('accounts', []):
                if is_initialize2_instruction(instruction):
                    return True
        return False
    except Exception as e:
        logger.error(f"Error checking for initialize2 instruction: {e}")
        return False


def is_initialize2_instruction(instruction):
    data = instruction.get("data")
    if data:
        try:
            missing_padding = len(data) % 4
            if missing_padding != 0:
                data += '=' * (4 - missing_padding)
            decoded_data = b64decode(data)
            
            instruction_layout = Struct(
                "opcode" / Int8ul,
            )
            deserialized = instruction_layout.parse(decoded_data)
            
            # Check if the opcode matches 'initialize2'
            if deserialized.opcode == 2:  # Replace '2' with the correct opcode
                return True
        except Exception as e:
            logger.error(f"Error decoding instruction data: {e}")
    return False
