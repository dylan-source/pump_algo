import time
import csv
import requests
import logging
from config import TWEET_SCOUT_KEY


# Optional: logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TIME_TO_SLEEP = 2  # number of seconds to sleep between each API call

def tweet_scout_get_score(twitter_handle):
    """
    Calls the TweetScout API to get a Twitter score for a given handle.
    Expected response: {'score': 7} or similar.
    """
    try:
        headers = {
            'Accept': "application/json",
            'ApiKey': TWEET_SCOUT_KEY
        }
        url = f"https://api.tweetscout.io/v2/score/{twitter_handle}"
        response = requests.get(url=url, headers=headers)
        score_json = response.json()
        return score_json  # e.g. {'score': <some_value>}
    except Exception as e:
        logger.error(f"TweetScout get_score error: {e}")
        time.sleep(TIME_TO_SLEEP)
        return {}

def main():
    # List of Twitter handles
    twitter_handles = [
        "pepexbtai",
        "ovumexperiment",
        "OlivAI",
        "Mites_AI",
        "DISCIPLINEDAI",
        "echoAGNT",
        "Inderji25835235",
        "Scanfeed",
        "SentiumAI",
        "HBCB_Token",
        "thred_dot_ai",
        "elysiumaisol",
        "WeWillBuildIt",
        "PurgeAI",
        "TimescaleDB",
        "Awwwonsui_",
        "search",
        "ADAWifeLover",
        "Spectrum_AiFi",
        "Gravity_Open",
        "pmtateuk",
        "Pijall1",
        "sqcportal",
        "GYROSatSOLANA",
        "BaconBully",
        "consequently",
        "OctopusSolAI",
        "XFashion",
        "thenest_hub",
        "ai6900z_",
        "zaidmukaddam",
        "shitoshi__",
        "cute_yoko",
        "0xVaultedAi",
        "aeroaitrade",
        "NeurliteNET",
        "pragma_solana",
        "OG_Alien_Sol",
        "search",
        "DEGA_org",
        "0xGremlin69",
        "Basital39824155",
        "OpticAIapp",
        "textmorgan",
        "stratafi_ai"
    ]

    # Open CSV file for writing
    with open("update_twitter_scores.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Write header
        writer.writerow(["twitter_handle", "score"])

        # For each handle, call the function, parse the score, and write to CSV
        for handle in twitter_handles:
            print(handle)
            score_data = tweet_scout_get_score(handle)
            # The response is expected to have a key 'score'; default to None if missing
            score_value = score_data.get("score", None)

            writer.writerow([handle, score_value])

            # Wait 2 seconds to avoid potential rate limits
            time.sleep(TIME_TO_SLEEP)

if __name__ == "__main__":
    main()
