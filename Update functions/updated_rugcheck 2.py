# from filter_utils import rugcheck_analysis
# import asyncio
# import httpx
# import csv
# import pandas as pd
# import time
# import os

# # Load your token addresses from the CSV file
# token_file_path = '/Users/dylanmartens/Documents/Coding/Pump sniping/pump_sniping_trade_new_listener_2/tokens.csv'
# token_data = pd.read_csv(token_file_path)

# # Ensure the CSV has a 'token_address' column
# if 'token_address' not in token_data.columns:
#     raise ValueError("CSV must contain a 'token_address' column.")

# async def process_tokens():
#     async with httpx.AsyncClient() as client:
#         processed_count = 0

#         # We'll collect partial results in a separate list
#         partial_results = []

#         for index, row in token_data.iterrows():
#             token_mint_address = row['token_address']
#             processed_count += 1

#             print(f"Processing {token_mint_address} ({processed_count}/{len(token_data)})")

#             try:
#                 metadata, risks, holder_metrics = await rugcheck_analysis(
#                     client, token_mint_address, download_image=False
#                 )
#                 result = {
#                     'token_mint_address': token_mint_address,
#                     'metadata': metadata,
#                     'risks': risks,
#                     'holder_metrics': holder_metrics
#                 }
#             except Exception as e:
#                 print(f"Error processing {token_mint_address}: {e}")
#                 # Store the error entry so we know this token had an error
#                 result = {
#                     'token_mint_address': token_mint_address,
#                     'metadata': None,
#                     'risks': None,
#                     'holder_metrics': None
#                 }

#             partial_results.append(result)

#             # Save progress every 10 tokens
#             if processed_count % 10 == 0:
#                 save_partial_results(partial_results, append=True)
#                 # Clear partial_results so we don't duplicate entries next time
#                 partial_results.clear()

#             # Sleep for 2 seconds to avoid rate limiting
#             time.sleep(2)

#         # If there are leftover results that haven't been saved yet, save them now
#         if partial_results:
#             save_partial_results(partial_results, append=True)

#         print("Finished processing all tokens.")

# def save_partial_results(results, append=False):
#     """
#     Flatten the results and save them to CSV.
#     If append=True, we open in append mode and do not write the header
#     unless the file doesn't exist yet.
#     """
#     output_file_path = '/Users/dylanmartens/Documents/Coding/Pump sniping/pump_sniping_trade_new_listener_2/tokens_processed.csv'

#     # Flatten each result (convert lists/dicts to string, etc.)
#     flattened_results = []
#     for result in results:
#         flat_result = {
#             'token_address': result['token_mint_address'],
#             'metadata': str(result['metadata']),
#             'risks': str(result['risks']),
#             'holder_metrics': str(result['holder_metrics'])
#         }
#         flattened_results.append(flat_result)

#     # Determine if we should write a header
#     mode = 'a' if append else 'w'
#     write_header = not append or not os.path.exists(output_file_path)

#     output_df = pd.DataFrame(flattened_results)
#     output_df.to_csv(output_file_path, index=False, mode=mode, header=write_header)

#     print(f"Progress saved to {output_file_path}")

# async def main():
#     await process_tokens()

# if __name__ == "__main__":
#     asyncio.run(main())

from filter_utils import rugcheck_analysis
import asyncio
import httpx
import csv
import pandas as pd
import time
import os

# File paths
TOKEN_FILE_PATH = '/Users/dylanmartens/Documents/Coding/Pump sniping/pump_sniping_trade_new_listener_2/tokens.csv'
PROCESSED_FILE_PATH = '/Users/dylanmartens/Documents/Coding/Pump sniping/pump_sniping_trade_new_listener_2/tokens_processed.csv'

# Load your token addresses from the CSV file
token_data = pd.read_csv(TOKEN_FILE_PATH)

# Ensure the CSV has a 'token_address' column
if 'token_address' not in token_data.columns:
    raise ValueError("CSV must contain a 'token_address' column.")

def load_already_processed_tokens():
    """
    Load all already processed tokens from PROCESSED_FILE_PATH, 
    if the file exists, into a set for quick membership checking.
    """
    if os.path.exists(PROCESSED_FILE_PATH):
        processed_df = pd.read_csv(PROCESSED_FILE_PATH)

        # Ensure the processed file has a compatible column
        if 'token_address' not in processed_df.columns:
            raise ValueError(f"{PROCESSED_FILE_PATH} must contain a 'token_address' column.")
        
        return set(processed_df['token_address'].unique())
    else:
        return set()

async def process_tokens():
    async with httpx.AsyncClient() as client:
        # Load any already processed tokens
        already_processed = load_already_processed_tokens()
        processed_count = 0

        # We'll collect partial results in a separate list
        partial_results = []

        total_tokens = len(token_data)

        for index, row in token_data.iterrows():
            token_mint_address = row['token_address']

            # Skip tokens that have already been processed
            if token_mint_address in already_processed:
                print(f"Skipping {token_mint_address} (already processed).")
                continue

            processed_count += 1
            print(f"Processing {token_mint_address} ({processed_count}/{total_tokens})")

            try:
                metadata, risks, holder_metrics = await rugcheck_analysis(
                    client, token_mint_address, download_image=False
                )
                result = {
                    'token_mint_address': token_mint_address,
                    'metadata': metadata,
                    'risks': risks,
                    'holder_metrics': holder_metrics
                }
            except Exception as e:
                print(f"Error processing {token_mint_address}: {e}")
                # Store the error entry so we know this token had an error
                result = {
                    'token_mint_address': token_mint_address,
                    'metadata': None,
                    'risks': None,
                    'holder_metrics': None
                }

            partial_results.append(result)

            # Save progress every 10 tokens
            if processed_count % 10 == 0:
                save_partial_results(partial_results, append=True)
                # Clear partial_results so we don't duplicate entries next time
                partial_results.clear()

            # Sleep for 2 seconds to avoid rate limiting
            time.sleep(0.5)

        # If there are leftover results that haven't been saved yet, save them now
        if partial_results:
            save_partial_results(partial_results, append=True)

        print("Finished processing all tokens.")

def save_partial_results(results, append=False):
    """
    Flatten the results and save them to CSV.
    If append=True, we open in append mode and do not write the header
    unless the file doesn't exist yet.
    """
    flattened_results = []
    for result in results:
        flat_result = {
            'token_address': result['token_mint_address'],
            'metadata': str(result['metadata']),
            'risks': str(result['risks']),
            'holder_metrics': str(result['holder_metrics'])
        }
        flattened_results.append(flat_result)

    mode = 'a' if append else 'w'
    write_header = not append or not os.path.exists(PROCESSED_FILE_PATH)

    output_df = pd.DataFrame(flattened_results)
    output_df.to_csv(PROCESSED_FILE_PATH, index=False, mode=mode, header=write_header)

    print(f"Progress saved to {PROCESSED_FILE_PATH}")

async def main():
    await process_tokens()

if __name__ == "__main__":
    asyncio.run(main())
