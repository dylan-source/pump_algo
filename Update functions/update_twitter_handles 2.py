import pandas as pd
import requests
import time
import logging
import csv
from config import TWEET_SCOUT_KEY

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TweetScout")

# Constants
TIME_TO_SLEEP = 5
CSV_FILE_PATH = 'migration_data_original.csv'
UPDATED_CSV_FILE_PATH = 'migration_data_updated.csv'
twitter_results = {}


def save_dict_to_csv(data_dict, output_file_path):
    with open(output_file_path, mode='w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        
        # Write the header
        writer.writerow(["Twitter Handle", "Value"])
        
        # Write the data
        for key, value in data_dict.items():
            writer.writerow([key, value])


def tweet_scout_get_recycled_handles(twitter_handle):

    try:
        querystring = {"link": twitter_handle}
        headers={'Accept': "application/json",'ApiKey': TWEET_SCOUT_KEY}
        url = f"https://api.tweetscout.io/v2/handle-history"

        response = requests.get(url=url, headers=headers, params=querystring)
        
        handle_info = response.json()
        # print(handle_info)
        if handle_info.get("message", ""):
            return {"handles_count": 1, "previous_handles": [handle_info]}
        else:              
            handles = handle_info["handles"]
            count = len(handles)
            return {"handles_count": count, "previous_handles": handles}
    except Exception as e:
        logger.error(f"TweetScout get_user_info error: {e}")
        time.sleep(TIME_TO_SLEEP)
        return {}



def load_twitter_handles():
    # Read the CSV file
    df = pd.read_csv(CSV_FILE_PATH)
    rows_count = 0

    # Check for the required column 'twitter_handle'
    if 'twitter_handle' not in df.columns:
        logger.error("The required column 'twitter_handle' is missing from the CSV.")
        return {}

    # Filter out invalid Twitter handles (those that are "FALSE" or NaN)
    valid_handles = df['twitter_handle'].dropna().str.upper() != "FALSE"
    handles = df.loc[valid_handles, 'twitter_handle']

    # Create a dictionary with each handle as a key and an empty dictionary as the value
    twitter_handles_dict = {handle: {} for handle in handles}

    logger.info(f"Loaded {len(twitter_handles_dict)} valid Twitter handles.")
    # return twitter_handles_dict

    for key, value in twitter_handles_dict.items():
        print(key)
        result = tweet_scout_get_recycled_handles(key)
        twitter_results[key] = result
        # rows_count += 1
        time.sleep(2)
        
        # if rows_count >= 5:
        #     print(twitter_results)
        #     break

    save_dict_to_csv(twitter_results, "updated_twitter.csv")

if __name__ == "__main__":
    twitter_handles_dict = load_twitter_handles()
