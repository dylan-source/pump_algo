import asyncio
import os
from solders.keypair import Keypair # type: ignore
import base64
import base58
import mimetypes
import re
from urllib.parse import urlparse
import asyncio
import time
import httpx
import requests
from config import WALLET_ADDRESS, SIGNATURE, TWEET_SCOUT_KEY, TIME_TO_SLEEP, TIMEOUT, PRIVATE_KEY, RAYDIUM_ADDRESS, migrations_logger
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from trade_utils_raydium import get_raydium_price

# TweetScout endpoint to get twitter ID from the username. The also have the reverse endpoing (get handle from ID)
# https://api.tweetscout.io/v2/handle-to-id/{user_handle}

# Check to see if DexScreener enhanced listing has been paid 
async def get_dex_paid(httpx_client, token_mint_address):
    try:
        response = await httpx_client.get(f'https://api.dexscreener.com/orders/v1/solana/{token_mint_address}', headers={})
        data = response.json()
    
        if not data:
            return False, data
        return True, data
    
    except Exception as e:
        migrations_logger.error(f'Dexscreener error: {e}')
        time.sleep(TIME_TO_SLEEP)
        return None, None


# Get number and breakdown of followers
async def tweet_scout_get_followers(twitter_handle):
    # response: {'followers_count': 7, 'influencers_count': 0, 'projects_count': 0, 'venture_capitals_count': 0, 'user_protected': False}
    try:
        headers = {'Accept': 'application/json', 'ApiKey': TWEET_SCOUT_KEY}
        params = {'user_handle': twitter_handle}
        url = 'https://api.tweetscout.io/v2/followers-stats'

        response = requests.get(url=url, headers=headers, params=params, timeout=30)
        data = response.json()
        return data
    
    except Exception as e:
        migrations_logger.error(f'TweetScout get_followers error: {e}')
        time.sleep(TIME_TO_SLEEP)
        return {}


# Get the TweetScout score
async def tweet_scout_get_score(twitter_handle):
    # response: {'score': 7}
    try:
        headers = {'Accept': 'application/json', 'ApiKey': TWEET_SCOUT_KEY}
        url = f'https://api.tweetscout.io/v2/score/{twitter_handle}'
        
        response = requests.get(url=url, headers=headers)
        score = response.json()
        return score
    
    except Exception as e:
        migrations_logger.error(f'TweetScout get_score error: {e}')
        time.sleep(TIME_TO_SLEEP)
        return {}


# Get top20 followers - ranked by TweetScout score
async def tweet_scout_get_top_followers(twitter_handle):
    # response is a list of dictionaries with followers details
    try:
        headers = {'Accept': 'application/json', 'ApiKey': TWEET_SCOUT_KEY}
        url = f'https://api.tweetscout.io/v2/top-followers/{twitter_handle}'
        response = requests.get(url=url, headers=headers)
        score = response.json()
        return score
    except Exception as e:
        migrations_logger.error(f'TweetScout get_top_followers error: {e}')
        time.sleep(TIME_TO_SLEEP)
        return []


# Provides info about the user account
async def tweet_scout_get_user_info(twitter_handle):
    # dictionary response with these keys: {'id', 'name', 'screen_name', 'description', 'followers_count', 'friends_count', 'register_date', 'tweets_count', 'banner', 'verified', 'avatar', 'can_dm'}
    try:
        headers = {'Accept': 'application/json', 'ApiKey': TWEET_SCOUT_KEY}
        url = f'https://api.tweetscout.io/v2/info/{twitter_handle}'
        response = requests.get(url=url, headers=headers)
        user_info = response.json()
        return user_info
    except Exception as e:
        migrations_logger.error(f'TweetScout get_user_info error: {e}')
        time.sleep(TIME_TO_SLEEP)
        return {}


# Checks to see if a twitter handle has been recycled
async def tweet_scout_get_recycled_handles(twitter_handle):
    try:
        querystring = {'link': twitter_handle}
        headers = {'Accept': 'application/json', 'ApiKey': TWEET_SCOUT_KEY}
        url = 'https://api.tweetscout.io/v2/handle-history'

        response = requests.get(url=url, headers=headers, params=querystring)
        handle_info = response.json()
        
        if handle_info.get('message', ''):
            return {'handles_count': 1, 'previous_handles': []}
        else:
            handles = handle_info['handles']
            count = len(handles)
            return {'handles_count': count, 'previous_handles': handles}
    except Exception as e:
        migrations_logger.error(f'TweetScout get_user_info error: {e}0')
        time.sleep(TIME_TO_SLEEP)
        return {}
    

# CoinGecko scraper
async def get_gecko_terminal_data(pool_id: str, headless=True, timeout=TIMEOUT):
    """
    Fetches three data points from GeckoTerminal for a given Solana pool:
      1) 'Bundled Buy %' (li:nth-child(2))
      2) 'Creator's Token Launches' (li:nth-child(5))
      3) 'CoinGecko Score' (span.text-sell.!leading-none.text-2xl)

    Returns a dict with 'bundled_buy_percent', 'creator_token_launches', 'coingecko_score'.
    If a timeout occurs on any data point, returns None for that specific value.
    """
    url = f"https://www.geckoterminal.com/solana/pools/{pool_id}"

    # CSS selectors for the three data points
    bundled_buy_selector = (
        "#__next > div > main > "
        "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
        "md\\:gap-y-0.md\\:px-4 > "
        "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
        "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
        "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
        "div.hidden.flex-col.gap-2.md\\:flex > "
        "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
        "div.flex-col.gap-y-3.flex > "
        "div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > "
        "ul > li:nth-child(2) > "
        "div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span"
    )
    creator_token_launches_selector = (
        "#__next > div > main > "
        "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
        "md\\:gap-y-0.md\\:px-4 > "
        "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
        "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
        "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
        "div.hidden.flex-col.gap-2.md\\:flex > "
        "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
        "div.flex-col.gap-y-3.flex > "
        "div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > "
        "ul > li:nth-child(5) > "
        "div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span"
    )

    async with async_playwright() as p:
        # Launch browser in headless mode with some stealth-friendly args
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/114.0.5735.110 Safari/537.36"
        )
        page = await context.new_page()

        # Optionally set default timeouts (milliseconds)
        page.set_default_timeout(timeout)
        page.set_default_navigation_timeout(timeout)

        try:
            # Navigate to the page
            await page.goto(url, timeout=timeout)

            # BUNDLED BUY %
            try:
                await page.wait_for_selector(bundled_buy_selector, timeout=timeout)
                bundled_buy_percent = await page.locator(bundled_buy_selector).nth(0).inner_text()
            except PlaywrightTimeoutError:
                migrations_logger.error(f"{pool_id} Timed out waiting for Bundled Buy % selector")
                bundled_buy_percent = None

            # CREATOR TOKEN LAUNCHES
            try:
                await page.wait_for_selector(creator_token_launches_selector, timeout=timeout)
                creator_token_launches = await page.locator(creator_token_launches_selector).nth(0).inner_text()
            except PlaywrightTimeoutError:
                migrations_logger.error(f"{pool_id} Timed out waiting for Creator's Token Launches selector.")
                creator_token_launches = None

            return {"bundled_buy_percent": bundled_buy_percent, "creator_token_launches": creator_token_launches}

        except PlaywrightTimeoutError:
            migrations_logger.error("Timeout error on CoinGecko")
            return {"bundled_buy_percent": None, "creator_token_launches": None}
        
        except Exception as e:
            migrations_logger.error(f"CoinGecko scraper error: {e}")
            return {"bundled_buy_percent": None, "creator_token_launches": None}

        finally:
            await browser.close()


# Get the "Chance of Cabal Coin" and Fake Volume from GateKept
async def gatekept_data(token_mint, timeout=120_000, headless=False):

    async with async_playwright() as p:
       
       # Launch browser in headless mode
        browser = await p.chromium.launch(headless=headless)

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/114.0.5735.110 Safari/537.36"
        )
        page = await context.new_page()

        # page = await browser.new_page()
        # await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"}) # -> set custom headers to mimick normal browser

        try:
            # Go to GateKept
            await page.goto("https://gatekept.io/", wait_until="networkidle")

            # Fill the input using the placeholder text and click the "Search" button
            await page.get_by_placeholder("Enter A Solana Token").fill(token_mint)

            await asyncio.sleep(3)
            await page.locator(".search-button").click()

            # Wait for the "Loading" text in p.cabal-chance-value to finish
            await page.wait_for_function(
                """
                () => {
                    const el = document.querySelector("p.cabal-chance-value");
                    return el && el.textContent.trim() !== "Loading...";
                }
                """,
                timeout=timeout
            )

            # Once finished loading, get the value from p.cabal-chance-value
            cabal_chance = await page.inner_text("p.cabal-chance-value")

            # Next, wait for the container with class="meta-value-container" to appear
            # await page.wait_for_selector("div.meta-value-container", timeout=timeout)
            fake_volume = await page.inner_text("div.meta-value-container")

            return cabal_chance, fake_volume

        except TimeoutError as e:
            migrations_logger.error("GateKept timeout occurred:")
            return None, None
        
        except Exception as e:
            migrations_logger.error("GateKept other error occurred:")
            return None, None

        finally:
            # Ensure the browser is always closed
            await browser.close()


# Function to get the RugCheck.xyz authentication message
async def generate_rugcheck_signature():
    """
    Generates the signature and wallet address for Rugcheck authentication,
    and stores them in the .env file as RUGCHECK_SIGNATURE and WALLET_ADDRESS.
    """
    # private_key_base58 = os.getenv('PRIVATE_KEY')
    # if not private_key_base58:
    #     migrations_logger.error('Private key not found in .env file.')
    #     return
    # try:
    #     private_key_bytes = base58.b58decode(private_key_base58)
    # except Exception as e:
    #     migrations_logger.error('Invalid private key format. Ensure it\'s base58-encoded.')
    #     return
    # keypair = Keypair.from_bytes(private_key_bytes)

    # Fetch the private key to sign the challenge message
    keypair = PRIVATE_KEY
    
    # Challenge message received from Rugcheck.xyz
    challenge_message = 'Please sign this message for authentication.'
    message_bytes = challenge_message.encode('utf-8')
    signature = keypair.sign_message(message_bytes)

    # Convert the Signature object to raw bytes and then base64 encode it
    signature_base64 = base64.b64encode(bytes(signature)).decode('utf-8')
    wallet_address = str(keypair.pubkey())

    # Log and return the result
    migrations_logger.info(f'Wallet Address: {wallet_address}')
    migrations_logger.info(f'Signature: {signature_base64}')
    return signature_base64, wallet_address


# Fetches token details from RugCheck.xyz
async def fetch_token_details(httpx_client: httpx.AsyncClient, token_mint_address: str):
    """
    Fetches token details from the Rugcheck "Tokens" endpoint.
    Args:
        httpx_client (httpx.AsyncClient): The async HTTP client instance from main.py.
        token_mint_address (str): The token mint address to query.
    Returns:
        dict: The response from the Rugcheck API containing token details.
    """
    
    # Return None is no RugCheck signature or wallet address
    if not SIGNATURE or not WALLET_ADDRESS:
        migrations_logger.error('RUGCHECK_SIGNATURE or WALLET_ADDRESS not found in environment. Run generate_rugcheck_signature first.')
        return None
    
    # Rugcheck Tokens endpoint
    tokens_url = f'https://api.rugcheck.xyz/v1/tokens/{token_mint_address}/report'
    
    # Prepare headers for the request
    headers = {'Authorization': f'{SIGNATURE}', 'Content-Type': 'application/json'}
    
    # Make the GET request using the provided async client
    try:
        response = await httpx_client.get(tokens_url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            migrations_logger.error(f'Failed to fetch token details: {response.status_code} {response.text}')
            migrations_logger.error(f'Test to see json conversion: {response.json()}')
            return None
    except Exception as e:
        migrations_logger.error(f'Error during API call: {str(e)}')
        return None


# Uses the IPFS url to get the twitter address
async def fetch_twitter_from_ipfs(httpx_client: httpx.AsyncClient, mint_address: str, token_metadata_uri: str):
    """
    Fetches the Twitter address from the token's metadata on IPFS.

    Args:
        httpx_client (httpx.AsyncClient): The async HTTP client instance from main.py.
        mint_address (str): The mint address of the token.
        token_metadata_uri (str): The IPFS URI from the token metadata.

    Returns:
        str: The Twitter address if found, or a message indicating it's not available.
    """
    try:
        # Convert the IPFS URI to a public gateway URL
        if token_metadata_uri.startswith('ipfs://'):
            ipfs_cid = token_metadata_uri.replace('ipfs://', '')
            ipfs_url = f'https://ipfs.io/ipfs/{ipfs_cid}'
        else: 
            ipfs_url = token_metadata_uri

        # Fetch the metadata from IPFS   
        response = await httpx_client.get(ipfs_url)
        if response.status_code!= 200:
            migrations_logger.error(f'Failed to fetch IPFS content. Status code: {response.status_code}0')
            return None
        
        # Fetch the metadata and extract the twitter address
        metadata = response.json()
        twitter_address = metadata.get('twitter')
        if twitter_address:
            return twitter_address
        else:  
            migrations_logger.info('Twitter address not found in the metadata.')
            return None
        
    except Exception as e:
            migrations_logger.error(f'Error fetching Twitter address: {str(e)}')
            return None


# Use the RugCheck response to get the token metadata
def fetch_token_metadata(token_details: dict):
    """
    Extracts token name, symbol, description, creator address, and decimals from token details.

    Args:
        token_details (dict): The output from fetch_token_details function.

    Returns:
        dict: A dictionary containing the token metadata.
    """
    try:
        metadata = {
            'name': token_details.get('tokenMeta', {}).get('name', 'Unknown'), 
            'symbol': token_details.get('tokenMeta', {}).get('symbol', 'Unknown'), 
            'description': token_details.get('tokenMeta', {}).get('description', 'Unknown'), 
            'creator': token_details.get('creator', 'Unknown'), 
            'decimals': token_details.get('token', {}).get('decimals', 'Unknown')
            }
        return metadata
    except Exception as e:
        migrations_logger.error(f'Error extracting token metadata: {str(e)}')
        return None
    

# Analyse the token holders
def holder_analysis(token_details: dict):
    """
    Performs a holder analysis based on the token details.
    Args:
        token_details (dict): The response from fetch_token_details function.
    Returns:
        dict: A dictionary containing the holder analysis metrics.
    """
    try:
        top_holders = token_details.get('topHolders', [])
        
        # Filter out Raydium address and insiders
        non_raydium_holders = [h for h in top_holders if h['address']!= RAYDIUM_ADDRESS]
        insiders = [h for h in top_holders if h.get('insider', False)]
        
        # Calculate metrics
        total_pct_top_5 = sum((h['pct'] for h in non_raydium_holders[:5]))
        total_pct_top_10 = sum((h['pct'] for h in non_raydium_holders[:10]))
        total_pct_top_20 = sum((h['pct'] for h in non_raydium_holders[:20]))
        total_pct_insiders = sum((h['pct'] for h in insiders))
        
        # Compile a token holder analysis dictionary
        return {
            'total_pct_top_5': total_pct_top_5, 
            'total_pct_top_10': total_pct_top_10, 
            'total_pct_top_20': total_pct_top_20, 
            'total_pct_insiders': total_pct_insiders
            }
    
    except Exception as e:
        migrations_logger.error(f'Error during holder analysis: {str(e)}')
        return None


# Download token image from IPFS - useful for reverse image search
async def download_token_image(httpx_client: httpx.AsyncClient, token_details: dict, save_path: str='./images'):
    """
    Downloads the token's image from the IPFS URL provided in the metadata.

    Args:
        httpx_client (httpx.AsyncClient): The async HTTP client instance from main.py.
        token_details (dict): The response from fetch_token_details function.
        save_path (str): Directory path to save the downloaded image.

    Returns:
        str: The file path of the downloaded image if successful, else None.
    """
    try:
        image_url = token_details.get('fileMeta', {}).get('image')
        if not image_url:
            migrations_logger.error('No image URL found in token metadata.')
            return None
        
        # Extract the file extension from the content type
        response = await httpx_client.get(image_url, follow_redirects=True)
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type')
            extension = mimetypes.guess_extension(content_type)
            
            if not extension:
                migrations_logger.error(f'Unable to determine file extension for content type: {content_type}')
                return None
            
            # Save the file with the correct extension
            file_name = image_url.split("/")[-1].split("?")[0]  # Remove query parameters if any
            os.makedirs(save_path, exist_ok=True)
            file_path = os.path.join(save_path, f"{file_name}{extension}")

            with open(file_path, "wb") as file:
                file.write(response.content)

            return file_path
        
        else:  
            migrations_logger.error(f'Failed to download image. Status code: {response.status_code}')
            return None
       
    except Exception as e:
        migrations_logger.error(f'Error downloading image: {str(e)}')
        return None
    

# Extract the risks identified from RugCheck
def identify_risks(token_details: dict):
    """
    Identifies risks based on the token details.

    Args:
        token_details (dict): The response from fetch_token_details function.

    Returns:
        dict: A dictionary containing the list of risk names and the total risk score.
    """
    try:
        risks = token_details.get('risks', [])
        risk_names = [risk.get('name', 'Unknown') for risk in risks]
        total_score = sum((risk.get('score', 0) for risk in risks))
        
        return {
            'risks': risk_names, 
            'score': total_score
            }
        
    except Exception as e:
        migrations_logger.error(f'Error identifying risks: {str(e)}')
        return None


# Get all the relevant data from IPFS
async def get_ipfs_data(httpx_client: httpx.AsyncClient, token_metadata_uri: str):
    """
    Extracts Twitter, website, and Telegram URLs from the IPFS metadata.
    Args:
        token_metadata_uri (str): The IPFS URI containing the metadata.
    Returns:
        dict: A dictionary with the Twitter, website, and Telegram URLs (or None if not found).
    """
    try:
        if not token_metadata_uri:
            migrations_logger.error('No IPFS metadata URI provided.')
            return {
                'ipfs_url': None, 
                'ifps_description': None, 
                'twitter': None, 
                'website': None, 
                'telegram': None
                }
        
        # Convert IPFS URI to public gateway URL
        if token_metadata_uri.startswith('ipfs://'):
            ipfs_cid = token_metadata_uri.replace('ipfs://', '')
            ipfs_url = f'https://ipfs.io/ipfs/{ipfs_cid}'
        else:  
            ipfs_url = token_metadata_uri

        # Fetch metadata
        response = await httpx_client.get(ipfs_url, follow_redirects=True)
        if response.status_code!= 200:
            migrations_logger.error(f'Failed to fetch IPFS metadata. Status code: {response.status_code}')
            return {
                'ipfs_url': ipfs_url, 
                'ifps_description': None, 
                'twitter': None, 
                'website': None, 
                'telegram': None
                }
        
        # Parse the metadata
        metadata = response.json()
        ipfs_description = metadata.get("description") or None
        twitter = metadata.get('twitter') or None
        website = metadata.get('website') or None
        telegram = metadata.get('telegram') or None
        return {
            'ipfs_url': ipfs_url, 
            'ifps_description': ipfs_description, 
            'twitter': twitter, 
            'website': website, 
            'telegram': telegram
            }

    except Exception as e:
        # migrations_logger.error(f'Error fetching IPFS data: {str(e)}')
        return {
            'ipfs_url': None, 
            'ifps_description': None, 
            'twitter': None, 
            'website': None, 
            'telegram': None
            }
    

# Extract the Twitter handle from the url
def extract_twitter_handle_or_false(url: str):
    """
    Attempt to extract a Twitter/X handle from the given URL.
    If the URL is not a valid Twitter/X user profile link,
    return False.
    
    Examples of valid user-profile URLs:
        - https://twitter.com/Jack
        - https://x.com/ai_marketonsol
        - https://twitter.com/Jack/
        - x.com/pepexbtai  (No scheme, but still valid)
    
    Examples of invalid URLs:
        - https://twitter.com/intent/post?text=...
        - https://twitter.com/anything/else
        - Something that doesn't match user handle patterns
    """
    # Return False if no URL is provided
    if url is None:
        return False
    
    # If the URL does not start with a scheme, prepend "https://".
    if not url.lower().startswith(('http://', 'https://')):
        url = 'https://' + url

    parsed = urlparse(url)

    # Filter out invalid domains
    valid_domains = {'twitter.com', 'x.com'}
    if parsed.netloc.lower() not in valid_domains:
        return False
    
    # Strip leading and trailing slashes from the path
    # e.g. "/Jack/" -> "Jack"
    path = parsed.path.strip('/')
    if not path:
        return False
    
    # Ensure there's no further slash inside the path 
    # (which would indicate more than just a simple handle)
    if '/' in path:
        return False
    
    # Check if the path is a valid Twitter/X handle (alphanumeric or underscore)
    handle_pattern = re.compile('^[A-Za-z0-9_]+$')
    if not handle_pattern.match(path):
        return False
    
    return path


# Old twitter handle extraction from the url function
def parse_twitter_handle(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path.lstrip('/')


# Is the website valid
def is_valid_website(url: str) -> bool:
    """
    Returns True if the URL domain is NOT in the disallowed list,
    otherwise returns False.
    """

    DISALLOWED_DOMAINS = [
        'twitter.com', 
        'tiktok.com', 
        'discord.com', 
        'youtube.com', 
        'instagram.com', 
        'google.com',
        'x.com', 
        'github.com', 
        'drive.google.com', 
        'facebook.com', 
        't.me', 
        'pypi.org', 
        'reddit.com', 
        'en.wikipedia.org', 
        't.co', 
        'telegram.com'
        ]
    
    parsed_url = urlparse(url.lower())
    domain = parsed_url.netloc
    
    # Remove any leading "www." (or other subdomains) for comparison
    # so that "www.twitter.com" and "twitter.com" are treated the same.
    if domain.startswith('www.'):
        domain = domain[4:]

    # Check if the domain ends with any of the disallowed domains    
    for d in DISALLOWED_DOMAINS:
        # For example, "twitter.com" should match "api.twitter.com", 
        # so we check endswith(). However, you might refine this if 
        # you only want exact matches.
        if domain.endswith(d):
            return False

    # Return True is filters are passed
    return True


# Original function to check if the website is valid
def is_domain_allowed(url: str) -> bool:
    """
    Check if a URL's domain is NOT in a list of forbidden domains.
    Returns True if it passes (i.e., it's allowed),
    or False if it's one of the forbidden domains.
    """

    forbidden_domains = {
        'x.com', 
        'google.com', 
        'github.com', 
        'drive.google.com', 
        'twitter.com', 
        'youtube.com', 
        'instagram.com', 
        'facebook.com', 
        't.me', 
        'pypi.org', 
        'reddit.com', 
        'en.wikipedia.org', 
        't.co', 
        'discord.com', 
        'tiktok.com', 
        'telegram.com'
        }
    
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    # Strip common prefixes like "www."
    if domain.startswith('www.'):
        domain = domain[4:]

    # If there's no domain, it's invalid
    if not domain:
        return False
    
    # If the domain is in the forbidden list, return False
    if domain in forbidden_domains:
        return False
    
    # Otherwise, it's allowed
    return True


# RugCheck wrapper function
async def rugcheck_analysis(httpx_client: httpx.AsyncClient, token_mint_address: str, download_image: bool=False, save_path: str='./images'):
    """
    Performs a full Rugcheck analysis including token metadata, risks, and holder analysis.

    Args:
        token_mint_address (str): The mint address of the token.
        download_image (bool): If True, downloads the token's image. Defaults to False.
        save_path (str): Directory path to save the downloaded image if enabled.

    Returns:
        dict: A dictionary containing the analysis results.
    """
    try:
        token_details = await fetch_token_details(httpx_client, token_mint_address)
        if not token_details:
            # migrations_logger.error('Failed to fetch token details.')
            return None, None, None
        
        # Token metadata
        metadata = fetch_token_metadata(token_details)

        # IPFS data (social links)
        ipfs_data = await get_ipfs_data(httpx_client, token_details.get('tokenMeta', {}).get('uri', ''))
        metadata['ipfs_url'] = ipfs_data.get('ipfs_url', '')
        metadata['ipfs_description'] = ipfs_data.get('ifps_description', '')
        metadata['twitter_url'] = ipfs_data.get('twitter', '')
        metadata['twitter_handle'] = extract_twitter_handle_or_false(metadata['twitter_url'])
        metadata['telegram_url'] = ipfs_data.get('telegram', '')
        metadata['website_url'] = ipfs_data.get('website', '')

        if metadata['website_url'] and metadata['website_url'] is not None:
            metadata['website_valid'] = is_domain_allowed(metadata['website_url'])
        else:
            metadata['website_valid'] = False
        
        # Image URL
        image_url = token_details.get('fileMeta', {}).get('image')
        metadata['image_url'] = image_url

        # Download image if required
        if download_image and image_url:
            image_path = await download_token_image(httpx_client, token_details, token_mint_address, save_path)
            metadata['image_path'] = image_path
        
        # Risks and holder analysis
        risks = identify_risks(token_details)
        holder_metrics = holder_analysis(token_details)

        # logger.info(f"Rugcheck Analysis: {result}")
        return metadata, risks, holder_metrics
    
    except Exception as e:
        migrations_logger.error(f'Error during Rugcheck analysis: {str(e)}')
        return None, None, None


# Run the various token filters
async def process_new_tokens(httpx_client, token_address, pair_address):
    
    # Perform RugCheck analysis
    metadata, risks, holder_metrics = await rugcheck_analysis(httpx_client=httpx_client, token_mint_address=token_address)
    if metadata is None:
        return None, None
    
    migrations_logger.info(f'Rugcheck done for {token_address}')

    # Extract and log token symbol and name
    if metadata is not None:
        symbol = metadata.get('symbol', '')
        name = metadata.get('name', '')
        migrations_logger.info(f'Symbol: {symbol} - Name: {name}')
    else: 
        migrations_logger.error(f'Rugcheck error for: {token_address}')

    # Determine is DexScreener has been paid and log the result
    is_dex_paid_parsed, is_dex_paid_raw = await get_dex_paid(httpx_client=httpx_client, token_mint_address=token_address)
    migrations_logger.info(f'DexScreener done for {token_address}')

    # Get amount of SOL in the pool (more SOL = higher price)
    sol_reserves = await get_raydium_price(pair_address)

    # Perform trade filters and log the result
    filters_result = await trade_filters(risks, holder_metrics, is_dex_paid_parsed, sol_reserves)
    migrations_logger.info(f'Potential trade: {symbol} - {token_address} - {filters_result}')
    
    data_to_save = {
        'metadata': metadata, 
        'risks': risks, 
        'holder_metrics': holder_metrics, 
        'is_dex_paid_parsed': is_dex_paid_parsed, 
        'is_dex_paid_raw': is_dex_paid_raw
        }
    
    return filters_result, data_to_save


# Trade logic function to determine if we trade a token or not
async def trade_filters(risks, holder_metrics, is_dex_paid_parsed, sol_reserves):
    """
        Current trade logic - return True if:
        - is_dex_paid_parsed: TRUE
        - holders_total_pct_top_5: <50%
        - risk_holder_interaction_5: <35%
        - twitter_handles_count: [0,1] -> paused for now
    """

    if risks is None or holder_metrics is None or sol_reserves is None:
        return False

    # Has the price increased from launch (LP is seeded with 79 SOL)
    price_change = sol_reserves - 79

    # Count how many risks there are after filtering out default pump.fun risks
    irrelevant_risks = ['Large Amount of LP Unlocked', 'Low Liquidity', 'Low amount of LP Providers']
    relevant_risks = [risk for risk in risks['risks'] if risk not in irrelevant_risks]
    relevant_risks_count = int(len(relevant_risks))

    # Calculate the risk-holder interaction score
    total_pct_top_5 = float(holder_metrics['total_pct_top_5'])
    risk_holder_interaction_5 = relevant_risks_count * total_pct_top_5

    # If all conditions are met return True else False
    if is_dex_paid_parsed==True and risk_holder_interaction_5<35 and total_pct_top_5<50 and price_change>0:
        return True
    else:
        return False