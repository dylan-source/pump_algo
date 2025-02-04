import asyncio
import os
from dotenv import load_dotenv, set_key
from solders.keypair import Keypair  # type: ignore
import base64
import base58
import httpx
import mimetypes
import re
from urllib.parse import urlparse
from config import WALLET_ADDRESS, SIGNATURE, logger

# Function to get the RugCheck.xyz authentication message
async def generate_rugcheck_signature():
    """
    Generates the signature and wallet address for Rugcheck authentication,
    and stores them in the .env file as RUGCHECK_SIGNATURE and WALLET_ADDRESS.
    """

    # Retrieve base58-encoded private key from the .env file
    private_key_base58 = os.getenv("PRIVATE_KEY")

    if not private_key_base58:
        logger.error("Private key not found in .env file.")
        return None

    try:
        # Decode the base58-encoded private key into bytes
        private_key_bytes = base58.b58decode(private_key_base58)
    except Exception as e:
        logger.error("Invalid private key format. Ensure it's base58-encoded.")
        return None

    # Create the Keypair object from the private key
    keypair = Keypair.from_bytes(private_key_bytes)

    # Challenge message received from Rugcheck.xyz
    challenge_message = "Please sign this message for authentication."
    message_bytes = challenge_message.encode('utf-8')
    signature = keypair.sign_message(message_bytes)

    # Convert the Signature object to raw bytes and then base64 encode it
    signature_base64 = base64.b64encode(bytes(signature)).decode('utf-8')
    wallet_address = str(keypair.pubkey())

    # If you want to persist these in the .env, uncomment the lines below:
    # env_path = os.getenv("DOTENV_PATH", ".env")  # Default to .env in current directory
    # set_key(env_path, "RUGCHECK_SIGNATURE", signature_base64)
    # set_key(env_path, "WALLET_ADDRESS", wallet_address)

    logger.info(f"Wallet Address: {wallet_address}")
    logger.info(f"Signature: {signature_base64}")

    return signature_base64, wallet_address


# Fetches data from RugCheck.xyz
async def fetch_token_details(httpx_client: httpx.AsyncClient, token_mint_address: str):
    """
    Fetches token details from the Rugcheck "Tokens" endpoint.

    Args:
        httpx_client (httpx.AsyncClient): The async HTTP client instance from main.py.
        token_mint_address (str): The token mint address to query.

    Returns:
        dict: The response from the Rugcheck API containing token details.
    """

    if not SIGNATURE or not WALLET_ADDRESS:
        logger.error("RUGCHECK_SIGNATURE or WALLET_ADDRESS not found in environment. "
                     "Run generate_rugcheck_signature first.")
        return None

    # Rugcheck Tokens endpoint
    tokens_url = f"https://api.rugcheck.xyz/v1/tokens/{token_mint_address}/report"

    # Prepare headers for the request
    headers = {
        "Authorization": f"Bearer {SIGNATURE}",
        "Content-Type": "application/json",
    }

    # Make the GET request using the provided async client
    try:
        response = await httpx_client.get(tokens_url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to fetch token details: {response.status_code} {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error during API call: {str(e)}")
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
        if token_metadata_uri.startswith("ipfs://"):
            ipfs_cid = token_metadata_uri.replace("ipfs://", "")
            ipfs_url = f"https://ipfs.io/ipfs/{ipfs_cid}"
        else:
            ipfs_url = token_metadata_uri

        # Fetch the metadata from IPFS
        response = await httpx_client.get(ipfs_url)
        if response.status_code != 200:
            logger.error(f"Failed to fetch IPFS content. Status code: {response.status_code}")
            return None

        metadata = response.json()

        # Extract the Twitter address from the metadata
        twitter_address = metadata.get("twitter")
        if twitter_address:
            return twitter_address
        else:
            logger.info("Twitter address not found in the metadata.")
            return None

    except Exception as e:
        logger.error(f"Error fetching Twitter address: {str(e)}")
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
            "name": token_details.get("tokenMeta", {}).get("name", "Unknown"),
            "symbol": token_details.get("tokenMeta", {}).get("symbol", "Unknown"),
            "description": token_details.get("tokenMeta", {}).get("description", "Unknown"),
            "creator": token_details.get("creator", "Unknown"),
            "decimals": token_details.get("token", {}).get("decimals", "Unknown")
        }
        return metadata
    except Exception as e:
        logger.error(f"Error extracting token metadata: {str(e)}")
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
        top_holders = token_details.get("topHolders", [])
        raydium_address = "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"

        # Filter out Raydium address and insiders
        non_raydium_holders = [h for h in top_holders if h["address"] != raydium_address]
        insiders = [h for h in top_holders if h.get("insider", False)]

        # Calculate metrics
        total_pct_top_5 = sum(h["pct"] for h in non_raydium_holders[:5])
        total_pct_top_10 = sum(h["pct"] for h in non_raydium_holders[:10])
        total_pct_top_20 = sum(h["pct"] for h in non_raydium_holders[:20])
        total_pct_insiders = sum(h["pct"] for h in insiders)

        analysis = {
            "total_pct_top_5": total_pct_top_5,
            "total_pct_top_10": total_pct_top_10,
            "total_pct_top_20": total_pct_top_20,
            "total_pct_insiders": total_pct_insiders,
        }
        return analysis

    except Exception as e:
        logger.error(f"Error during holder analysis: {str(e)}")
        return None


# Download token image from IPFS - useful for reverse image search
async def download_token_image(httpx_client: httpx.AsyncClient, token_details: dict, save_path: str = "./images"):
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
        image_url = token_details.get("fileMeta", {}).get("image")
        if not image_url:
            logger.error("No image URL found in token metadata.")
            return None

        response = await httpx_client.get(image_url, follow_redirects=True)
        if response.status_code == 200:
            # Determine the file type
            content_type = response.headers.get("Content-Type")
            extension = mimetypes.guess_extension(content_type)

            if not extension:
                logger.error(f"Unable to determine file extension for content type: {content_type}")
                return None

            # Save the file with the correct extension
            file_name = image_url.split("/")[-1].split("?")[0]  # Remove query parameters if any
            os.makedirs(save_path, exist_ok=True)
            file_path = os.path.join(save_path, f"{file_name}{extension}")

            with open(file_path, "wb") as file:
                # For streamed content, you can iterate over the response.aiter_bytes() as well
                file.write(response.content)

            return file_path
        else:
            logger.error(f"Failed to download image. Status code: {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Error downloading image: {str(e)}")
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
        risks = token_details.get("risks", [])
        risk_names = [risk.get("name", "Unknown") for risk in risks]
        total_score = sum(risk.get("score", 0) for risk in risks)

        result = {
            "risks": risk_names,
            "score": total_score
        }
        return result
    except Exception as e:
        logger.error(f"Error identifying risks: {str(e)}")
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
            logger.error("No IPFS metadata URI provided.")
            return {
                "ipfs_url": None,
                "ifps_description": None,
                "twitter": None,
                "website": None,
                "telegram": None,
            }

        # Convert IPFS URI to public gateway URL
        if token_metadata_uri.startswith("ipfs://"):
            ipfs_cid = token_metadata_uri.replace("ipfs://", "")
            ipfs_url = f"https://ipfs.io/ipfs/{ipfs_cid}"
        else:
            ipfs_url = token_metadata_uri

        # logger.info(f"Fetching metadata from IPFS (or custom gateway): {ipfs_url}")

        # Fetch metadata
        response = await httpx_client.get(ipfs_url, follow_redirects=True)
        if response.status_code != 200:
            logger.error(f"Failed to fetch IPFS metadata. Status code: {response.status_code}")
            return {
                "ipfs_url": ipfs_url,
                "ifps_description": None,
                "twitter": None,
                "website": None,
                "telegram": None,
            }

        # Parse the metadata
        metadata = response.json()
        ipfs_description = metadata.get("description") or None
        twitter = metadata.get("twitter") or None
        website = metadata.get("website") or None
        telegram = metadata.get("telegram") or None

        return {
            "ipfs_url": ipfs_url,
            "ifps_description": ipfs_description,
            "twitter": twitter,
            "website": website,
            "telegram": telegram,
        }

    except Exception as e:
        logger.error(f"Error fetching IPFS data: {str(e)}")
        return {
            "ipfs_url": None,
            "ifps_description": None,
            "twitter": None,
            "website": None,
            "telegram": None,
        }


# Extract the oonly twitter handles from the url
def extract_twitter_handle_or_false(url: str):
    """
    Attempt to extract a Twitter/X handle from the given URL.
    If the URL is not a valid Twitter/X user profile link,
    return False.
    
    Examples of valid user-profile URLs:
        - https://twitter.com/Jack
        - https://x.com/ai_marketonsol
        - https://twitter.com/Jack/
    
    Examples of invalid URLs:
        - https://twitter.com/intent/post?text=...
        - https://twitter.com/anything/else
        - Something that doesn't match user handle patterns
    """
    parsed = urlparse(url)
    
    # The domain might be "twitter.com" or "x.com".
    valid_domains = {"twitter.com", "x.com"}
    if parsed.netloc.lower() not in valid_domains:
        return False
    
    # Strip both leading and trailing slashes from the path
    # e.g. "/Jack/" -> "Jack"
    path = parsed.path.strip("/")
    
    # If the path is empty, it can't be a valid handle
    if not path:
        return False
    
    # If there's a slash left in the path after stripping, 
    # then it's not just a simple handle.
    # e.g. "Jack/status/12345"
    if "/" in path:
        return False
    
    # Check if the path is a valid Twitter/X handle (alphanumeric or underscore)
    handle_pattern = re.compile(r'^[A-Za-z0-9_]+$')
    if not handle_pattern.match(path):
        return False
    
    return path


# Old twitter handle extraction from the url function
def parse_twitter_handle(url: str) -> str:
    parsed = urlparse(url)
    # parsed.netloc would be 'x.com'
    # parsed.path would be '/ai_marketonsol'
    return parsed.path.lstrip('/')





# Is the website valid
def is_valid_website(url: str) -> bool:
    """
    Returns True if the URL domain is NOT in the disallowed list,
    otherwise returns False.
    """

    DISALLOWED_DOMAINS = [
        "twitter.com",
        "tiktok.com",
        "discord.com",
        "youtube.com",
        "instagram.com",
        "google.com",
    ]
    
    parsed_url = urlparse(url.lower())
    domain = parsed_url.netloc  # e.g. "www.twitter.com"

    # Remove any leading "www." (or other subdomains) for comparison
    # so that "www.twitter.com" and "twitter.com" are treated the same.
    if domain.startswith("www."):
        domain = domain[4:]
    
    # Check if the domain ends with any of the disallowed domains
    for d in DISALLOWED_DOMAINS:
        # For example, "twitter.com" should match "api.twitter.com", 
        # so we check endswith(). However, you might refine this if 
        # you only want exact matches.
        if domain.endswith(d):
            return False  # Not valid
    
    return True  # Valid if we never matched a disallowed domain


# Original function to check if the website is valid
def is_domain_allowed(url: str) -> bool:
    """
    Check if a URL's domain does NOT include any forbidden substrings.
    Returns True if it passes (i.e., it's allowed),
    or False if it's one of the forbidden domains.
    """
    # List of forbidden domains (lowercase).
    forbidden_substrings = [
        "google",
        "youtube",
        "twitter",
        "facebook",
        "reddit",
        "instagram",
        "tiktok",
        "discord"
    ]
    
    # Parse the URL
    parsed = urlparse(url)
    domain = parsed.netloc.lower()  # netloc is the domain + optional port

    # Strip common prefixes like "www."
    if domain.startswith("www."):
        domain = domain[4:]
    
    # If there's no domain (e.g., user just typed "hello"), it's invalid.
    if not domain:
        return False
    
    # Check if the domain contains any forbidden substring
    if any(forbidden in domain for forbidden in forbidden_substrings):
        return False
    
    # Passed all checks
    return True


# RugCheck wrapper function
async def rugcheck_analysis(httpx_client: httpx.AsyncClient, token_mint_address: str, download_image: bool = False, save_path: str = "./images"):
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
            logger.error("Failed to fetch token details.")
            return None

        # Token metadata
        metadata = fetch_token_metadata(token_details)

        # IPFS data (social links)
        ipfs_data = await get_ipfs_data(httpx_client, token_details.get("tokenMeta", {}).get("uri", ""))
        metadata["ipfs_url"] = ipfs_data.get("ipfs_url", "")
        metadata["ipfs_description"] = ipfs_data.get("ifps_description", "")
        metadata["twitter_url"] = ipfs_data.get("twitter", "")
        metadata["twitter_handle"] = extract_twitter_handle_or_false(metadata["twitter_url"])
        metadata["telegram_url"] = ipfs_data.get("telegram", "")
        metadata["website_url"] = ipfs_data.get("website", "")

        if metadata["website_url"]:
            metadata["website_valid"] = is_domain_allowed(metadata["website_url"])
        else:
            metadata["website_valid"] = False

        # Image URL
        image_url = token_details.get("fileMeta", {}).get("image")
        metadata["image_url"] = image_url

        # Download image if required
        if download_image and image_url:
            image_path = await download_token_image(httpx_client, token_details, token_mint_address, save_path)
            metadata["image_path"] = image_path

        # Risks and holder analysis
        risks = identify_risks(token_details)
        holder_metrics = holder_analysis(token_details)

        # logger.info(f"Rugcheck Analysis: {result}")
        return metadata, risks, holder_metrics

    except Exception as e:
        logger.error(f"Error during Rugcheck analysis: {str(e)}")
        return None, None, None





httpx_client = httpx.AsyncClient(timeout=10)
if __name__ == "__main__":

    metadata, risks, holder_metrics = asyncio.run(rugcheck_analysis(httpx_client=httpx_client, token_mint_address="Eijt4UJtAjRpPtL1oMGCoCcvRrL5BXpjfiYGE3aZpump"))
    print(metadata)
    print(risks)
    print(holder_metrics)


    