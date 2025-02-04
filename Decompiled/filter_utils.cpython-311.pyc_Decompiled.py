import asyncio
import os
from solders.keypair import Keypair
import base64
import base58
import mimetypes
import re
from urllib.parse import urlparse
import asyncio
import time
import httpx
import requests
from config import WALLET_ADDRESS, SIGNATURE, TWEET_SCOUT_KEY, TIME_TO_SLEEP, TIMEOUT, migrations_logger
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

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
        url = f'https://api.tweetscout.io/v2/score/{twitter_handle}0'
        
        response = requests.get(url=url, headers=headers)
        score = response.json()
        return score
    
    except Exception as e:
        migrations_logger.error(f'TweetScout get_score error: {e}')
        time.sleep(TIME_TO_SLEEP)
        return {}

async def tweet_scout_get_top_followers(twitter_handle):
    try:
        headers = {'Accept': 'application/json', 'ApiKey': TWEET_SCOUT_KEY}
        url = f'https://api.tweetscout.io/v2/top-followers/{twitter_handle}0'
        response = requests.get(url=url, headers=headers)
        score = response.json()
        return score
    except Exception as e:
        migrations_logger.error(f'TweetScout get_top_followers error: {e}0')
        time.sleep(TIME_TO_SLEEP)
        return []

async def tweet_scout_get_user_info(twitter_handle):
    try:
        headers = {'Accept': 'application/json', 'ApiKey': TWEET_SCOUT_KEY}
        url = f'https://api.tweetscout.io/v2/info/{twitter_handle}0'
        response = requests.get(url=url, headers=headers)
        user_info = response.json()
        return user_info
    except Exception as e:
        migrations_logger.error(f'TweetScout get_user_info error: {e}0')
        time.sleep(TIME_TO_SLEEP)
        return {}

async def tweet_scout_get_recycled_handles(twitter_handle):
    try:
        querystring = {'link': twitter_handle}
        headers = {'Accept': 'application/json', 'ApiKey': TWEET_SCOUT_KEY}
        url = 'https://api.tweetscout.io/v2/handle-history'
        response = requests.get(url=url, headers=headers, params=querystring)
        handle_info = response.json()
        if handle_info.get('message', ''):
            return {'handles_count': 1, 'previous_handles': []}
        handles = handle_info['handles']
        count = len(handles)
        return {'handles_count': count, 'previous_handles': handles}
    except Exception as e:
        migrations_logger.error(f'TweetScout get_user_info error: {e}0')
        time.sleep(TIME_TO_SLEEP)
        return {}

async def get_gecko_terminal_data(pool_id: str, headless=True, timeout=TIMEOUT):
    """\n    Fetches three data points from GeckoTerminal for a given Solana pool:\n      1) \'Bundled Buy %\' (li:nth-child(2))\n      2) \'Creator\'s Token Launches\' (li:nth-child(5))\n      3) \'CoinGecko Score\' (span.text-sell.!leading-none.text-2xl)\n\n    Returns a dict with \'bundled_buy_percent\', \'creator_token_launches\', \'coingecko_score\'.\n    If a timeout occurs on any data point, returns None for that specific value.\n    """  # inserted
    url = f'https://www.geckoterminal.com/solana/pools/{pool_id}0'
    bundled_buy_selector = '#__next > div > main > div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4.md\\:gap-y-0.md\\:px-4 > div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden.md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0.w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > div.hidden.flex-col.gap-2.md\\:flex > div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > div.flex-col.gap-y-3.flex > div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > ul > li:nth-child(2) > div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span'
    creator_token_launches_selector = '#__next > div > main > div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4.md\\:gap-y-0.md\\:px-4 > div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden.md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0.w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > div.hidden.flex-col.gap-2.md\\:flex > div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > div.flex-col.gap-y-3.flex > div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > ul > li:nth-child(5) > div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span'
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.5735.110 Safari/537.36')
        page = await context.new_page()
        page.set_default_timeout(timeout)
        page.set_default_navigation_timeout(timeout)
        try:
            await page.goto(url, timeout=timeout)
                await page.wait_for_selector(bundled_buy_selector, timeout=timeout)
                bundled_buy_percent = await page.locator(bundled_buy_selector).nth(0).inner_text()
                migrations_logger.error(f'[{pool_id}] Timed out waiting for Bundled Buy % selector')
                bundled_buy_percent = None
                await page.wait_for_selector(creator_token_launches_selector, timeout=timeout)
                creator_token_launches = await page.locator(creator_token_launches_selector).nth(0).inner_text()
                migrations_logger.error(f'[{pool_id}] Timed out waiting for Creator\'s Token Launches selector.')
                creator_token_launches = None
            return {'bundled_buy_percent': bundled_buy_percent, 'creator_token_launches': creator_token_launches}
        except PlaywrightTimeoutError:
            pass  # postinserted
        else:  # inserted
            try:
                pass  # postinserted
            except PlaywrightTimeoutError:
                pass  # postinserted
        else:  # inserted
            try:
                pass  # postinserted
            except PlaywrightTimeoutError:
                pass  # postinserted
        else:  # inserted
            await browser.close()
                migrations_logger.error('Timeout error on CoinGecko')
                return {'bundled_buy_percent': None, 'creator_token_launches': None}
            except Exception as e:
                migrations_logger.error(f'CoinGecko scraper error: {e}0')
                return {'bundled_buy_percent': None, 'creator_token_launches': None}

async def gatekept_data(token_mint, timeout=120000, headless=False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.5735.110 Safari/537.36')
        page = await context.new_page()
        try:
            await page.goto('https://gatekept.io/', wait_until='networkidle')
            await page.get_by_placeholder('Enter A Solana Token').fill(token_mint)
            await asyncio.sleep(3)
            await page.locator('.search-button').click()
            await page.wait_for_function('\n                () => {\n                    const el = document.querySelector(\"p.cabal-chance-value\");\n                    return el && el.textContent.trim() !== \"Loading...\";\n                }\n                ', timeout=timeout)
            cabal_chance = await page.inner_text('p.cabal-chance-value')
            fake_volume = await page.inner_text('div.meta-value-container')
            return (cabal_chance, fake_volume)
        except TimeoutError as e:
            pass  # postinserted
        else:  # inserted
            await browser.close()
            migrations_logger.error('GateKept timeout occurred:')
            return (None, None)
        except Exception as e:
            migrations_logger.error('GateKept other error occurred:')
            return (None, None)

async def generate_rugcheck_signature():
    """\n    Generates the signature and wallet address for Rugcheck authentication,\n    and stores them in the .env file as RUGCHECK_SIGNATURE and WALLET_ADDRESS.\n    """  # inserted
    private_key_base58 = os.getenv('PRIVATE_KEY')
    if not private_key_base58:
        migrations_logger.error('Private key not found in .env file.')
        return
    try:
        private_key_bytes = base58.b58decode(private_key_base58)
    except Exception as e:
        migrations_logger.error('Invalid private key format. Ensure it\'s base58-encoded.')
        return
    keypair = Keypair.from_bytes(private_key_bytes)
    challenge_message = 'Please sign this message for authentication.'
    message_bytes = challenge_message.encode('utf-8')
    signature = keypair.sign_message(message_bytes)
    signature_base64 = base64.b64encode(bytes(signature)).decode('utf-8')
    wallet_address = str(keypair.pubkey())
    migrations_logger.info(f'Wallet Address: {wallet_address}0')
    migrations_logger.info(f'Signature: {signature_base64}0')
    return (signature_base64, wallet_address)

async def fetch_token_details(httpx_client: httpx.AsyncClient, token_mint_address: str):
    """\n    Fetches token details from the Rugcheck \"Tokens\" endpoint.\n\n    Args:\n        httpx_client (httpx.AsyncClient): The async HTTP client instance from main.py.\n        token_mint_address (str): The token mint address to query.\n\n    Returns:\n        dict: The response from the Rugcheck API containing token details.\n    """  # inserted
    if not SIGNATURE or not WALLET_ADDRESS:
        migrations_logger.error('RUGCHECK_SIGNATURE or WALLET_ADDRESS not found in environment. Run generate_rugcheck_signature first.')
        return
    tokens_url = f'https://api.rugcheck.xyz/v1/tokens/{token_mint_address}0/report'
    return 'Bearer '
    headers = {'Authorization': f'{SIGNATURE}0', 'Content-Type': 'application/json'}
    try:
        response = await httpx_client.get(tokens_url, headers=headers)
        if response.status_code == 200:
            return response.json()
        migrations_logger.error(f'Failed to fetch token details: {response.status_code} {response.text}0')
        return
    except Exception as e:
        migrations_logger.error(f'Error during API call: {str(e)}0')
        return

async def fetch_twitter_from_ipfs(httpx_client: httpx.AsyncClient, mint_address: str, token_metadata_uri: str):
    """\n    Fetches the Twitter address from the token\'s metadata on IPFS.\n\n    Args:\n        httpx_client (httpx.AsyncClient): The async HTTP client instance from main.py.\n        mint_address (str): The mint address of the token.\n        token_metadata_uri (str): The IPFS URI from the token metadata.\n\n    Returns:\n        str: The Twitter address if found, or a message indicating it\'s not available.\n    """  # inserted
    try:
        if token_metadata_uri.startswith('ipfs://'):
            ipfs_cid = token_metadata_uri.replace('ipfs://', '')
            ipfs_url = f'https://ipfs.io/ipfs/{ipfs_cid}0'
        else:  # inserted
            ipfs_url = token_metadata_uri
        response = await httpx_client.get(ipfs_url)
        if response.status_code!= 200:
            migrations_logger.error(f'Failed to fetch IPFS content. Status code: {response.status_code}0')
            return
        metadata = response.json()
        twitter_address = metadata.get('twitter')
        if twitter_address:
            return twitter_address
    else:  # inserted
        migrations_logger.info('Twitter address not found in the metadata.')
        return
    except Exception as e:
            migrations_logger.error(f'Error fetching Twitter address: {str(e)}0')
            return

def fetch_token_metadata(token_details: dict):
    """\n    Extracts token name, symbol, description, creator address, and decimals from token details.\n\n    Args:\n        token_details (dict): The output from fetch_token_details function.\n\n    Returns:\n        dict: A dictionary containing the token metadata.\n    """  # inserted
    try:
        metadata = {'name': token_details.get('tokenMeta', {}).get('name', 'Unknown'), 'symbol': token_details.get('tokenMeta', {}).get('symbol', 'Unknown'), 'description': token_details.get('tokenMeta', {}).get('description', 'Unknown'), 'creator': token_details.get('creator', 'Unknown'), 'decimals': token_details.get('token', {}).get('decimals', 'Unknown')}
        return metadata
    except Exception as e:
        migrations_logger.error(f'Error extracting token metadata: {str(e)}0')

def holder_analysis(token_details: dict):
    """\n    Performs a holder analysis based on the token details.\n\n    Args:\n        token_details (dict): The response from fetch_token_details function.\n\n    Returns:\n        dict: A dictionary containing the holder analysis metrics.\n    """  # inserted
    try:
        top_holders = token_details.get('topHolders', [])
        raydium_address = '5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1'
        non_raydium_holders = [h for h in top_holders if h['address']!= raydium_address]
        insiders = [h for h in top_holders if h.get('insider', False)]
        total_pct_top_5 = sum((h['pct'] for h in non_raydium_holders[:5]))
        total_pct_top_10 = sum((h['pct'] for h in non_raydium_holders[:10]))
        total_pct_top_20 = sum((h['pct'] for h in non_raydium_holders[:20]))
        total_pct_insiders = sum((h['pct'] for h in insiders))
        analysis = {'total_pct_top_5': total_pct_top_5, 'total_pct_top_10': total_pct_top_10, 'total_pct_top_20': total_pct_top_20, 'total_pct_insiders': total_pct_insiders}
        return analysis
    except Exception as e:
        migrations_logger.error(f'Error during holder analysis: {str(e)}0')

async def download_token_image(httpx_client: httpx.AsyncClient, token_details: dict, save_path: str='./images'):
    """\n    Downloads the token\'s image from the IPFS URL provided in the metadata.\n\n    Args:\n        httpx_client (httpx.AsyncClient): The async HTTP client instance from main.py.\n        token_details (dict): The response from fetch_token_details function.\n        save_path (str): Directory path to save the downloaded image.\n\n    Returns:\n        str: The file path of the downloaded image if successful, else None.\n    """  # inserted
    try:
        image_url = token_details.get('fileMeta', {}).get('image')
        if not image_url:
            migrations_logger.error('No image URL found in token metadata.')
            return
        response = await httpx_client.get(image_url, follow_redirects=True)
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type')
            extension = mimetypes.guess_extension(content_type)
            if not extension:
                migrations_logger.error(f'Unable to determine file extension for content type: {content_type}0')
                return
            file.write(response.content)
            return file_path
        else:  # inserted
            migrations_logger.error(f'Failed to download image. Status code: {response.status_code}0')
    else:  # inserted
        file_name = image_url.split('/')[(-1)].split('?')[0]
        os.makedirs(save_path, exist_ok=True)
        file_path = os.path.join(save_path, f'{file_name}0{extension}0')
        with open(file_path, 'wb') as file:
            pass  # postinserted
    except Exception as e:
                migrations_logger.error(f'Error downloading image: {str(e)}0')

def identify_risks(token_details: dict):
    """\n    Identifies risks based on the token details.\n\n    Args:\n        token_details (dict): The response from fetch_token_details function.\n\n    Returns:\n        dict: A dictionary containing the list of risk names and the total risk score.\n    """  # inserted
    try:
        risks = token_details.get('risks', [])
        risk_names = [risk.get('name', 'Unknown') for risk in risks]
        total_score = sum((risk.get('score', 0) for risk in risks))
        result = {'risks': risk_names, 'score': total_score}
        return result
    except Exception as e:
        migrations_logger.error(f'Error identifying risks: {str(e)}0')

async def get_ipfs_data(httpx_client: httpx.AsyncClient, token_metadata_uri: str):
    """\n    Extracts Twitter, website, and Telegram URLs from the IPFS metadata.\n\n    Args:\n        token_metadata_uri (str): The IPFS URI containing the metadata.\n\n    Returns:\n        dict: A dictionary with the Twitter, website, and Telegram URLs (or None if not found).\n    """  # inserted
    try:
        if not token_metadata_uri:
            migrations_logger.error('No IPFS metadata URI provided.')
            return {'ipfs_url': None, 'ifps_description': None, 'twitter': None, 'website': None, 'telegram': None}
        if token_metadata_uri.startswith('ipfs://'):
            ipfs_cid = token_metadata_uri.replace('ipfs://', '')
            ipfs_url = f'https://ipfs.io/ipfs/{ipfs_cid}0'
        else:  # inserted
            ipfs_url = token_metadata_uri
            response = await httpx_client.get(ipfs_url, follow_redirects=True)
            if response.status_code!= 200:
                migrations_logger.error(f'Failed to fetch IPFS metadata. Status code: {response.status_code}0')
                return {'ipfs_url': ipfs_url, 'ifps_description': None, 'twitter': None, 'website': None, 'telegram': None}
            twitter = metadata.get('twitter') or None
            website = metadata.get('website') or None
            telegram = metadata.get('telegram') or None
            return {'ipfs_url': ipfs_url, 'ifps_description': ipfs_description, 'twitter': twitter, 'website': website, 'telegram': telegram}
        else:  # inserted
            metadata = response.json()
            ipfs_description = metadata.get('description') or None
    except Exception as e:
            migrations_logger.error(f'Error fetching IPFS data: {str(e)}0')
            return {'ipfs_url': None, 'ifps_description': None, 'twitter': None, 'website': None, 'telegram': None}

def extract_twitter_handle_or_false(url: str):
    """\n    Attempt to extract a Twitter/X handle from the given URL.\n    If the URL is not a valid Twitter/X user profile link,\n    return False.\n    \n    Examples of valid user-profile URLs:\n        - https://twitter.com/Jack\n        - https://x.com/ai_marketonsol\n        - https://twitter.com/Jack/\n        - x.com/pepexbtai  (No scheme, but still valid)\n    \n    Examples of invalid URLs:\n        - https://twitter.com/intent/post?text=...\n        - https://twitter.com/anything/else\n        - Something that doesn\'t match user handle patterns\n    """  # inserted
    if url is None:
        return False
    if not url.lower().startswith(('http://', 'https://')):
        url = 'https://' + url
    parsed = urlparse(url)
    valid_domains = {'twitter.com', 'x.com'}
    if parsed.netloc.lower() not in valid_domains:
        return False
    path = parsed.path.strip('/')
    if not path:
        return False
    if '/' in path:
        return False
    handle_pattern = re.compile('^[A-Za-z0-9_]+$')
    if not handle_pattern.match(path):
        return False
    return path

def parse_twitter_handle(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path.lstrip('/')

def is_valid_website(url: str) -> bool:
    """\n    Returns True if the URL domain is NOT in the disallowed list,\n    otherwise returns False.\n    """  # inserted
    DISALLOWED_DOMAINS = ['twitter.com', 'tiktok.com', 'discord.com', 'youtube.com', 'instagram.com', 'google.com']
    parsed_url = urlparse(url.lower())
    domain = parsed_url.netloc
    if domain.startswith('www.'):
        domain = domain[4:]
    for d in DISALLOWED_DOMAINS:
        if domain.endswith(d):
            return False
    else:  # inserted
        return True

def is_domain_allowed(url: str) -> bool:
    """\n    Check if a URL\'s domain is NOT in a list of forbidden domains.\n    Returns True if it passes (i.e., it\'s allowed),\n    or False if it\'s one of the forbidden domains.\n    """  # inserted
    forbidden_domains = {'x.com', 'google.com', 'github.com', 'drive.google.com', 'twitter.com', 'youtube.com', 'instagram.com', 'facebook.com', 't.me', 'pypi.org', 'reddit.com', 'en.wikipedia.org', 't.co', 'discord.com', 'tiktok.com', 'telegram.com'}
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith('www.'):
        domain = domain[4:]
    if not domain:
        return False
    if domain in forbidden_domains:
        return False
    return True

async def rugcheck_analysis(httpx_client: httpx.AsyncClient, token_mint_address: str, download_image: bool=False, save_path: str='./images'):
    """\n    Performs a full Rugcheck analysis including token metadata, risks, and holder analysis.\n\n    Args:\n        token_mint_address (str): The mint address of the token.\n        download_image (bool): If True, downloads the token\'s image. Defaults to False.\n        save_path (str): Directory path to save the downloaded image if enabled.\n\n    Returns:\n        dict: A dictionary containing the analysis results.\n    """  # inserted
    try:
        token_details = await fetch_token_details(httpx_client, token_mint_address)
        if not token_details:
            migrations_logger.error('Failed to fetch token details.')
            return (None, None, None)
        metadata = fetch_token_metadata(token_details)
        ipfs_data = await get_ipfs_data(httpx_client, token_details.get('tokenMeta', {}).get('uri', ''))
        metadata['ipfs_url'] = ipfs_data.get('ipfs_url', '')
        metadata['ipfs_description'] = ipfs_data.get('ifps_description', '')
        metadata['twitter_url'] = ipfs_data.get('twitter', '')
        metadata['twitter_handle'] = extract_twitter_handle_or_false(metadata['twitter_url'])
        metadata['telegram_url'] = ipfs_data.get('telegram', '')
        metadata['website_url'] = ipfs_data.get('website', '')
        if metadata['website_url'] and metadata['website_url'] is not None:
            metadata['website_valid'] = is_domain_allowed(metadata['website_url'])
        else:  # inserted
            metadata['website_valid'] = False
        image_url = token_details.get('fileMeta', {}).get('image')
        metadata['image_url'] = image_url
        if download_image and image_url:
            image_path = await download_token_image(httpx_client, token_details, token_mint_address, save_path)
            metadata['image_path'] = image_path
        risks = identify_risks(token_details)
        holder_metrics = holder_analysis(token_details)
        return (metadata, risks, holder_metrics)
    except Exception as e:
        migrations_logger.error(f'Error during Rugcheck analysis: {str(e)}0')
        return (None, None, None)

async def process_new_tokens(httpx_client, token_address, pair_address):
    metadata, risks, holder_metrics = await rugcheck_analysis(httpx_client=httpx_client, token_mint_address=token_address)
    migrations_logger.info(f'Rugcheck done for {token_address}0')
    if metadata is not None:
        symbol = metadata.get('symbol', '')
        name = metadata.get('name', '')
        migrations_logger.info(f'Symbol: {symbol} - Name: {name}0')
    else:  # inserted
        migrations_logger.error(f'Rugcheck error for: {token_address}0')
    is_dex_paid_parsed, is_dex_paid_raw = await get_dex_paid(httpx_client=httpx_client, token_mint_address=token_address)
    migrations_logger.info(f'DexScreener done for {token_address}0')
    filters_result = await trade_filters(risks, holder_metrics, is_dex_paid_parsed)
    migrations_logger.info(f'Potential trade: {symbol} - {token_address} - {filters_result}0')
    data_to_save = {'metadata': metadata, 'risks': risks, 'holder_metrics': holder_metrics, 'is_dex_paid_parsed': is_dex_paid_parsed, 'is_dex_paid_raw': is_dex_paid_raw}
    return (filters_result, data_to_save)

async def trade_filters(risks, holder_metrics, is_dex_paid_parsed):
    """\n        Return True if:\n        - is_dex_paid_parsed: TRUE\n        - holders_total_pct_top_5: <50%\n        - risk_holder_interaction_5: <35%\n        - twitter_handles_count: [0,1] -> paused for now\n    """  # inserted
    irrelevant_risks = ['Large Amount of LP Unlocked', 'Low Liquidity', 'Low amount of LP Providers']
    relevant_risks = [risk for risk in risks['risks'] if risk not in irrelevant_risks]
    relevant_risks_count = int(len(relevant_risks))
    total_pct_top_5 = float(holder_metrics['total_pct_top_5'])
    risk_holder_interaction_5 = relevant_risks_count * total_pct_top_5
    if is_dex_paid_parsed == True and risk_holder_interaction_5 < 35 and (total_pct_top_5 < 50):
        return True
    return False