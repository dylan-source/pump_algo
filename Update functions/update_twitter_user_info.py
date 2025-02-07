import time
import csv
import requests
import logging
from config import TWEET_SCOUT_KEY

# Optional logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TIME_TO_SLEEP = 2  # seconds to wait between each API call

def tweet_scout_get_user_info(twitter_handle):
    """
    Fetches user info from TweetScout's v2/info endpoint.
    Example of expected response keys:
    {
      'id': ...,
      'name': ...,
      'screen_name': ...,
      'description': ...,
      'followers_count': ...,
      'friends_count': ...,
      'register_date': ...,
      'tweets_count': ...,
      'banner': ...,
      'verified': ...,
      'avatar': ...,
      'can_dm': ...
    }
    """
    print(f"{twitter_handle}")
    try:
        headers = {
            'Accept': 'application/json',
            'ApiKey': TWEET_SCOUT_KEY
        }
        url = f"https://api.tweetscout.io/v2/info/{twitter_handle}"
        response = requests.get(url=url, headers=headers)
        user_info = response.json()
        print(f"{user_info}")
        return user_info
    except Exception as e:
        # logger.error(f"TweetScout get_user_info error: {e}")
        time.sleep(TIME_TO_SLEEP)
        print(f"{e}")
        return {}

def main():
    # List of Twitter handles to query
    twitter_handles = [
        "pepexbtai",
        "ovumexperiment",
        "Mites_AI",
        "DISCIPLINEDAI",
        "echoAGNT",
        "Inderji25835235",
        "starkly_ai",
        "Scanfeed",
        "SentiumAI",
        "cleopetrafun",
        "ShadeXAI",
        "HBCB_Token",
        "AgoraLabAI",
        "thred_dot_ai",
        "solloveaccount",
        "WeWillBuildIt",
        "PurgeAI",
        "littletaleai",
        "search",
        "0xEchoLeaks",
        "ADAWifeLover",
        "luminossai",
        "Gravity_Open",
        "pmtateuk",
        "Pijall1",
        "snow__AI",
        "DropsMarketAI",
        "sqcportal",
        "fere_ai",
        "BaconBully",
        "consequently",
        "Geometrysol",
        "ai6900z_",
        "rengacollective",
        "shitoshi__",
        "cute_yoko",
        "0xVaultedAi",
        "aeroaitrade",
        "LiveChase70129",        
        "pragma_solana",
        "OG_Alien_Sol",
        "search",
        "DEGA_org",
        "0xGremlin69",
        "AGENTARCOS",
        "Basital39824155",
        "ai700x",
        "textmorgan",
        "stratafi_ai",
    ]

    # Open CSV file for writing
    with open("update_tweet_scout_user_info.csv", mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header row
        writer.writerow([
            "twitter_handle",
            "twitter_name",
            "twitter_screen_name",
            "twitter_description",
            "twitter_followers_count",
            "twitter_friends_count",
            "twitter_register_date",
            "twitter_tweets_count",
            "twitter_verified",
            "twitter_can_dm"
        ])

        # Process each handle, call API, then sleep to avoid rate-limit
        for handle in twitter_handles:
            user_info = tweet_scout_get_user_info(handle)

            # Extract fields from user_info with default values
            name = user_info.get('name', '')
            screen_name = user_info.get('screen_name', '')
            description = user_info.get('description', '')
            followers_count = user_info.get('followers_count', 0)
            friends_count = user_info.get('friends_count', 0)
            register_date = user_info.get('register_date', '')
            tweets_count = user_info.get('tweets_count', 0)
            verified = user_info.get('verified', False)
            can_dm = user_info.get('can_dm', False)

            # Write data to CSV
            writer.writerow([
                handle,
                name,
                screen_name,
                description,
                followers_count,
                friends_count,
                register_date,
                tweets_count,
                verified,
                can_dm
            ])

            # Wait 2 seconds to prevent hitting rate limits
            time.sleep(TIME_TO_SLEEP)

if __name__ == "__main__":
    main()
