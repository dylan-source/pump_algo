import time
import csv
import requests
import logging
from config import TWEET_SCOUT_KEY

# Replace with your actual TweetScout API key and any other configs
logging.basicConfig(level=logging.INFO)

def tweet_scout_get_recycled_handles(twitter_handle):
    """
    Provided function.
    Calls TweetScout to get recycled handle history.
    """
    try:
        querystring = {"link": twitter_handle}
        headers = {
            'Accept': "application/json",
            'ApiKey': TWEET_SCOUT_KEY
        }
        url = "https://api.tweetscout.io/v2/handle-history"

        response = requests.get(url=url, headers=headers, params=querystring)
        handle_info = response.json()

        if handle_info.get("message", ""):
            # If there's a 'message' key, it typically means no further data
            return {"handles_count": 1, "previous_handles": [handle_info]}
        else:
            # Otherwise, we expect "handles" to exist in the JSON
            handles = handle_info["handles"]
            count = len(handles)
            return {"handles_count": count, "previous_handles": handles}

    except Exception as e:
        logging.error(f"TweetScout get_user_info error: {e}")
        time.sleep(2)
        return {}

def main():
    # List of Twitter handles to check
    twitter_handles = [
        "soul_agents",
        "0xaico",
        "pepexbtai",
        "echoAGNT",
        "Inderji25835235",
        "SentiumAI",
        "thred_dot_ai",
        "WeWillBuildIt",
        "ADAWifeLover",
        "pmtateuk",
        "Pijall1",
        "consequently",
        "ai6900z_",
        "aeroaitrade",
        "Pijall1",  # duplicate included in provided list
        "pragma_solana",
        "Basital39824155",
        "textmorgan"
    ]

    # Open a CSV file for writing
    with open("update_twitter_recycled_output.csv", mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        # Write header row
        writer.writerow(["twitter_handle", "handles_count", "previous_handles"])

        # For each handle, call TweetScout, then sleep 2 seconds
        for handle in twitter_handles:
            
            data = tweet_scout_get_recycled_handles(handle)
            count = data.get("handles_count", 0)
            prev = data.get("previous_handles", [])
            print(f"{handle} - {count} - {prev}")

            # Write one row per handle
            writer.writerow([handle, count, prev])

            # Wait 2 seconds before next call
            time.sleep(2)

if __name__ == "__main__":
    main()
