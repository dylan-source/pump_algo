import re
import os
import time
import json
import asyncio
import csv
from typing import Callable, List, Dict
from telethon import TelegramClient
from dotenv import load_dotenv
from config import TG_RICK_BOT_USERNAME, TG_TRENCH_SCANNER_BOT_USERNAME, TG_PEPEBOOST_BOT_USERNAME, logger

# Load the relenvant environment variables
load_dotenv()

TG_API_ID = int(os.getenv("TG_API_ID"))
TG_API_HASH = os.getenv("TG_API_HASH")
TG_SESSION_NAME = os.getenv("TG_SESSION_NAME")

BOT_USERNAMES = {
    "RickBurpBot": TG_RICK_BOT_USERNAME,       # /dp, /twit, /web   docs: https://talk.markets/t/commands-on-telegram/1465
    "TrenchScannerBot": TG_TRENCH_SCANNER_BOT_USERNAME,  # /bundle
    # "PepeBoostBot": TG_PEPEBOOST_BOT_USERNAME
}
# Other bots to consider: 
#   @the_mugetsu_bot
#   @soul_scanner_bot
#   @SyraxScannerBot


# Error classes
class RateLimitError(Exception):
    """Raised when RickBurpBot indicates the 3 min cooldown is in effect."""
    pass

class ServerError(Exception):
    """Raised when TrenchScannerBot returns 'Server Error' for an invalid token."""
    pass


# Since there is more than 1 telegram bot, we've created a BotManager class
class BotManager:
    
    # Intialize the BotManager clss object
    def __init__(self):
        self.clients = {}
        # We use this to track the last time we called /web so we respect the 3-min limit
        self.last_web_command_time = None

    
    # Save the results to a CSV
    async def save_to_file(self, filename, content):
        safe_filename = filename.replace("/", "_")
        with open(safe_filename, "a", encoding="utf-8") as file:
            file.write(content + "\n")


    # Initialize the Telegram Client
    async def initialize_client(self, bot_name):
        if bot_name not in self.clients:
            session_name = f"{TG_SESSION_NAME}_{bot_name}"
            client = TelegramClient(session_name, TG_API_ID, TG_API_HASH)
            await client.start()
            self.clients[bot_name] = client

        return self.clients[bot_name]

    
    # Send commands and the arguments to the Telegramt bot
    async def send_command(self, bot_name, command, argument=""):
        client = await self.initialize_client(bot_name)
        bot_username = BOT_USERNAMES[bot_name]
        full_command = f"{command} {argument}".strip()

        print(f"Sending command to {bot_name}: {full_command}")
        await client.send_message(bot_username, full_command)

        # Let’s allow extra time for /bundle
        max_attempts = 15  # default ~30s
        if command == "/bundle":
            max_attempts = 20  # ~40s to allow more time for large data

        response_message = None
        consecutive_same_responses = 0

        for attempt in range(max_attempts):
            await asyncio.sleep(2)  # 2 seconds between polls
            messages = await client.get_messages(bot_username, limit=1)
            if not messages:
                print(f"[Attempt {attempt+1}] No messages found.")
                continue

            new_message = messages[0]
            if response_message is None:
                response_message = new_message
                print(f"[Attempt {attempt+1}] First message captured.")
                continue

            # Check if a brand-new message arrived (new ID)
            if new_message.id != response_message.id:
                response_message = new_message
                consecutive_same_responses = 0
                print(f"[Attempt {attempt+1}] Received a brand new message.")
            else:
                # Same message ID => possible edit
                if new_message.text != response_message.text:
                    response_message = new_message
                    consecutive_same_responses = 0
                    print(f"[Attempt {attempt+1}] Message text changed (edit).")
                else:
                    consecutive_same_responses += 1
                    print(f"[Attempt {attempt+1}] Message unchanged. "
                          f"Consecutive identical polls: {consecutive_same_responses}")
                    if consecutive_same_responses >= 2:
                        print("[INFO] Final response confirmed.")
                        break

        final_text = response_message.text if response_message else "No response received."
        await self.save_to_file(f"{bot_name}_{command}_final_output.txt", final_text)
        return final_text


    # Send a ping command to check that it's working and connected
    async def ping_rick_bot(self):
        """
        Sends a 'ping' command to RickBurpBot to ensure it is reachable and 
        the session is initialized properly.
        """
        try:
            response_text = await self.send_command("RickBurpBot", "/wubba")
            logger.info(f"[PING] RickBurpBot responded with:\n{response_text}")
        except Exception as e:
            logger.error(f"[PING] Failed to ping RickBurpBot: {e}")
            



    # Parse response to check if DexScreener socials have been paid
    def parse_dex_paid_response(self, response: str, raw_response: bool = False):
        """
        Check if the token is DexPaid or not. 
        Returns True/False/None or a dict with both 'raw_response' and 'parsed_result'
        """
        if "❌ DexScreener not paid" in response:
            parsed_result = False
        elif "DexPaid" in response and "not paid" not in response:
            parsed_result = True
        else:
            parsed_result = None  # Or handle unexpected text differently

        if raw_response:
            return {
                "raw_response": response,
                "parsed_result": parsed_result
            }
        else:
            return parsed_result

    
    # Parse response to check if the twitter username has been recycled
    def parse_twitter_recycled_response(self, response: str, raw_response: bool = False):
        """
        If "💩 User not found:" → user doesn't exist
        Else parse for multiple unique Twitters
        """
        if "💩 User not found:" in response:
            parsed_result = "twitter_user_not_found"
        else:
            usernames = re.findall(r"🕑.*?⋅\s\[(.*?)\]", response)
            unique_usernames = set(usernames)
            parsed_result = (len(unique_usernames) > 1)

        if raw_response:
            return {
                "raw_response": response,
                "parsed_result": parsed_result
            }
        else:
            return parsed_result

    
    # Parse response to check if the website has been copied
    def parse_is_website_similar_response(self, response: str, raw_response: bool = False):
        """
        Checks if the site is a possible clone, or if the bot is in cooldown.
        Raises RateLimitError on "3 min cooldown" text.
        """
        if "Burp.. the 3 min cooldown is still in effect." in response:
            raise RateLimitError("RickBurpBot is in the 3-minute cooldown period.")

        if "Rate limit triggered" in response:
            raise ValueError("Rate limit in effect. Please wait and try again.")

        flags = ['🚨', '🧬', '🤖']
        lines = response.split('\n')
        likely_copied = False
        flag_count = 0

        for line in lines:
            for flag in flags:
                if flag in line:
                    flag_count += 1
            if flag_count >= 2:
                likely_copied = True
                break
            flag_count = 0

        parsed_result = likely_copied
        if raw_response:
            return {
                "raw_response": response,
                "parsed_result": parsed_result
            }
        else:
            return parsed_result

    
    # Parse response to see if the there have been any transaction bundling
    def parse_bundle_response(self, response: str, raw_response: bool = False):
        """
        Parses the bundle analysis response.
        Raises ServerError if "Server Error" is found.
        If '⏳ Loading...' is still present, we never got a final response.
        """
        if "Server Error" in response:
            raise ServerError("TrenchScannerBot returned 'Server Error' for the provided token.")

        if "⏳ Loading bundle data..." in response:
            # We only saw the placeholder. Return or raise an error indicating incomplete result.
            if raw_response:
                return {
                    "raw_response": response,
                    "parsed_result": {
                        "error": "incomplete_bundle_data",
                        "message": "The bundle data never finalized before polling ended."
                    }
                }
            else:
                return {"error": "incomplete_bundle_data"}

        # Parse overall statistics
        overall_stats_pattern = re.compile(
            r"📦 Total Bundles: (\d+).*?"
            r"📊 Total Percentage Bundled: ([\d.]+)%.*?"
            r"📈 Current Held Percentage: ([\d.]+)%",
            re.DOTALL
        )
        overall_match = overall_stats_pattern.search(response)
        overall_stats = {
            "total_bundles": int(overall_match.group(1)) if overall_match else None,
            "total_percentage_bundled": float(overall_match.group(2)) if overall_match else None,
            "current_held_percentage": float(overall_match.group(3)) if overall_match else None,
        }

        # Parse Creator Risk Profile
        creator_risk_profile_pattern = re.compile(
            r"👨‍💻 Creator Risk Profile.*?"
            r"• Total Created: (\d+).*?"
            r"• Current Token Held %: ([\d.]+)%.*?"
            r"• ⚠️ RUG HISTORY: (.*?)\n",
            re.DOTALL
        )
        creator_match = creator_risk_profile_pattern.search(response)
        creator_risk_profile = {
            "total_created": int(creator_match.group(1)) if creator_match else None,
            "current_token_held_percentage": float(creator_match.group(2)) if creator_match else None,
            "rug_history": creator_match.group(3).strip() if creator_match else None,
        }

        # Parse top bundles
        top_bundles = []
        bundle_pattern = re.compile(
            r"Slot (\d+):.*?"
            r"💼 Unique Wallets: (\d+).*?"
            r"📊 % of Supply: ([\d.]+)%",
            re.DOTALL
        )
        wallet_threshold = 3
        supply_threshold = 10.0

        for match in bundle_pattern.finditer(response):
            unique_wallets = int(match.group(2))
            percentage_of_supply = float(match.group(3))
            if unique_wallets > wallet_threshold and percentage_of_supply > supply_threshold:
                top_bundles.append({
                    "slot": int(match.group(1)),
                    "unique_wallets": unique_wallets,
                    "percentage_of_supply": percentage_of_supply,
                })

        # Compile the parsed result
        parsed_result = {
            "overall_statistics": overall_stats,
            "creator_risk_profile": creator_risk_profile,
            "top_bundles": top_bundles,
        }

        if raw_response:
            return {
                "raw_response": response,
                "parsed_result": parsed_result
            }
        else:
            return parsed_result


    # Fallback default parser
    def default_parser(self, response, raw_response=False):
        """
        Default fallback parser
        """
        if raw_response:
            return {
                "raw_response": response,
                "parsed_result": {"raw_response_only": True}
            }
        else:
            return {"raw_response_only": True}

    
    # Parse response handler
    def parse_response(self, command: str, response: str, raw_response: bool = False):
        parsers = {
            "/dp": self.parse_dex_paid_response,
            "/twit": self.parse_twitter_recycled_response,
            "/web": self.parse_is_website_similar_response,
            "/bundle": self.parse_bundle_response
        }
        parser: Callable = parsers.get(command, self.default_parser)
        return parser(response, raw_response=raw_response)


    # Function to issue the relevant commands to the relevant bot
    async def process_token(self, token_mint: str, website: str = None, twitter: str = None):
        """
        Issues all the relevant commands:
          /twit, /web, /dp, /bundle
        and parses the responses.
        """
        results = {"token_mint": token_mint}
        parsed_results = {"token_mint": token_mint}

        # 1) Analyze Twitter
        if twitter:
            raw_twit_response = await self.send_command("RickBurpBot", "/twit", twitter)
            results["twitter_analysis"] = self.parse_response("/twit", raw_twit_response, raw_response=True)

        # 2) Analyze Website with 3-min limit logic
        if website:
            current_time = time.time()
            # If we've called /web recently, wait the remainder of 3 min
            if self.last_web_command_time:
                elapsed = current_time - self.last_web_command_time
                if elapsed < 180:  # 3 mins = 180 seconds
                    wait_time = 180 - elapsed
                    print(f"[INFO] Waiting {wait_time:.1f} seconds before sending /web...")
                    await asyncio.sleep(wait_time)

            raw_web_response = await self.send_command("RickBurpBot", "/web", website)
            try:
                parsed_web = self.parse_response("/web", raw_web_response, raw_response=True)
                results["website_analysis"] = parsed_web
            except RateLimitError:
                # Bot responded with cooldown anyway; wait 3 min, then retry once
                print("[WARN] 3 min cooldown triggered. Waiting 3 min before retrying /web...")
                await asyncio.sleep(180)

                raw_web_response = await self.send_command("RickBurpBot", "/web", website)
                parsed_web = self.parse_response("/web", raw_web_response, raw_response=True)
                results["website_analysis"] = parsed_web

            self.last_web_command_time = time.time()  # update last web call

        # 3) Check DexPaid: /dp
        #    We'll use RickBurpBot for that too, passing the token mint as the argument
        raw_dp_response = await self.send_command("RickBurpBot", "/dp", token_mint)
        results["dex_paid_analysis"] = self.parse_response("/dp", raw_dp_response, raw_response=True)

        # 4) Analyze Bundle using TrenchScannerBot
        raw_bundle_response = await self.send_command("TrenchScannerBot", "/bundle", token_mint)
        results["bundle_analysis"] = self.parse_response("/bundle", raw_bundle_response, raw_response=True)

        # Parse the results to JSON
        twit_info = results.get("twitter_analysis", {})
        parsed_results["twitter_parsed"] = json.dumps(twit_info.get("parsed_result", {}))
        parsed_results["twitter_raw"] = twit_info.get("raw_response", "")

        # Website
        web_info = results.get("website_analysis", {})
        parsed_results["website_parsed"] = json.dumps(web_info.get("parsed_result", {}))
        parsed_results["website_raw"] = web_info.get("raw_response", "")

        # Dex Paid (/dp)
        dp_info = results.get("dex_paid_analysis", {})
        parsed_results["dp_parsed"] = json.dumps(dp_info.get("parsed_result", {}))
        parsed_results["dp_raw"] = dp_info.get("raw_response", "")

        # Bundle
        bundle_info = results.get("bundle_analysis", {})
        parsed_results["bundle_parsed"] = json.dumps(bundle_info.get("parsed_result", {}))
        parsed_results["bundle_raw"] = bundle_info.get("raw_response", "")

        return results, parsed_results

