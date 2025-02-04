import csv
import time
import requests
import logging
from config import TWEET_SCOUT_KEY

# Optional: adjust logger configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TIME_TO_SLEEP = 2  # 2 seconds between calls

def tweet_scout_get_followers(twitter_handle):
    """
    Returns follower stats about a given Twitter handle from TweetScout.
    Example of response structure:
    {
      'followers_count': 7,
      'influencers_count': 0,
      'projects_count': 0,
      'venture_capitals_count': 0,
      'user_protected': False
    }
    """
    try:
        headers = {
            'Accept': "application/json",
            'ApiKey': TWEET_SCOUT_KEY
        }
        params = {"user_handle": twitter_handle}
        url = "https://api.tweetscout.io/v2/followers-stats"

        response = requests.get(url=url, headers=headers, params=params, timeout=30)
        data = response.json()
        return data
    except Exception as e:
        logger.error(f"TweetScout get_followers error: {e}")
        time.sleep(TIME_TO_SLEEP)
        return {}

def main():
    # List of Twitter handles you want to check
    twitter_handles_original = [
        "pepexbtai",
        "ovumexperiment",
        "Mites_AI",
        "DISCIPLINEDAI",
        "TheSoulAI",
        "echoAGNT",
        "Vapour_ai",
        "Inderji25835235",
        "mynameiskyliaa",
        "EnsembleCodes",
        "TheoriqAI",
        "Banks",
        "LarpAICoin",
        "Scanfeed",
        "finiti",
        "SentiumAI",
        "shizuonsolana",
        "cleopetrafun",
        "AresAIsol",
        "FartbookSol",
        "toonscoin",
        "ai_blurblur",
        "HBCB_Token",
        "AgoraLabAI",
        "thred_dot_ai",
        "gainzdotxyz",
        "deskybotfun",
        "TikTokBaddies",
        "SecureFinance_X",
        "mii_agent",
        "lobehub",
        "ai16zdao",
        "accelix0",
        "WeWillBuildIt",
        "rubikpuzzleAI",
        "sociopulseai",
        "biosphere3_ai",
        "PurgeAI",
        "KAFRAC0RP",
        "search",
        "ImChillaxx",
        "lightningonsol",
        "0xEchoLeaks",
        "JEETUSMAXIMUSAi",
        "ADAWifeLover",
        "MiriamAitoken",
        "BCSymph",
        "tttheangelsss",
        "Gravity_Open",
        "ailisa_agent",
        "zottoaioffical",
        "pmtateuk",
        "aibuttholesol",
        "rubenkgomez",
        "Pijall1",
        "Jars_AI_",
        "ChickoBird",
        "bonkaibuddy",
        "DropsMarketAI",
        "votebruv",
        "MiriamAitoken",
        "sqcportal",
        "Oil2025",
        "vibeonsolana",
        "GYROSatSOLANA",
        "AgeniusSol",
        "BaconBully",
        "consequently",
        "solstorm_com",
        "TheSolaAi",
        "cognitoailabs",
        "YuzaeAI",
        "chascoby_art",
        "XFashion",
        "vity_toolkit",
        "Tax_Ai_",
        "TaxifySolana",
        "lendaonchain",
        "_Black_Box_AI",
        "ai6900z_",
        "_AtomicAI",
        "mindmaze_ai",
        "shitoshi__",
        "conjureai",
        "cute_yoko",
        "0xVaultedAi",
        "SirisysAlpha",
        "speakai_agent",
        "SAKUAI_CLUB",
        "AtyraNews",
        "aeroaitrade",
        "RicketMachines",
        "Pijall1",
        "agent_tadz",
        "Sword_AI",
        "agentmacro",
        "Baby_Flork",
        "ChatLedgerly",
        "FBDanimation",
        "pragma_solana",
        "doublesolana",
        "walletvision",
        "lafd",
        "lafd",
        "OG_Alien_Sol",
        "search",
        "DEGA_org",
        "0xGremlin69",
        "TPASarah",
        "AGENTARCOS",
        "Basital39824155",
        "textmorgan",
        "stratafi_ai"
    ]

    twitter_handles = [
        "TikTokBaddies",
        "ai16zdao",
        "ailisa_agent",
        "MiriamAitoken",
        "chascoby_art",
        "ai6900z_",
        "RicketMachines",
        "TPASarah"]

    # Open CSV file for writing
    with open("followers_stats_updated.csv", mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        # Write header row
        writer.writerow([
            "twitter_handle",
            "total_followers",
            "total_influencers_count",
            "total_projects_count",
            "total_venture_capitals_count",
            "total_user_protected"
        ])

        # Iterate over each handle, get data, sleep 2s
        for handle in twitter_handles:
            print(handle)
            data = tweet_scout_get_followers(handle)

            followers_count = data.get("followers_count", 0)
            influencers_count = data.get("influencers_count", 0)
            projects_count = data.get("projects_count", 0)
            venture_capitals_count = data.get("venture_capitals_count", 0)
            user_protected = data.get("user_protected", False)

            writer.writerow([
                handle,
                followers_count,
                influencers_count,
                projects_count,
                venture_capitals_count,
                user_protected
            ])

            # Sleep 2 seconds before the next call
            time.sleep(TIME_TO_SLEEP)

if __name__ == "__main__":
    main()
