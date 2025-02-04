import asyncio
import httpx
import requests
from config import TWEET_SCOUT_KEY, TIMEOUT, logger
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_async

# Check to see if DexScreener enhanced listing has been paid 
async def get_dex_paid(httpx_client, token_mint_address):

    response = await httpx_client.get(
        f"https://api.dexscreener.com/orders/v1/solana/{token_mint_address}",
        headers={},
    )
    data = response.json()

    if not data:
        return False, data
    else:
        return True, data


# Get number and breakdown of followers
def tweet_scout_get_followers(twitter_handle):
    # response: {'followers_count': 7, 'influencers_count': 0, 'projects_count': 0, 'venture_capitals_count': 0, 'user_protected': False}

    headers={'Accept': "application/json",'ApiKey': TWEET_SCOUT_KEY}
    params = {"user_handle": twitter_handle}
    url = "https://api.tweetscout.io/v2/followers-stats"

    response = requests.get(url=url, headers=headers, params=params, timeout=30)
    
    data = response.json()
    return data


# Get the TweetScout score
def tweet_scout_get_score(twitter_handle):
    # response: {'score': 7}

    headers={'Accept': "application/json",'ApiKey': TWEET_SCOUT_KEY}
    url = f"https://api.tweetscout.io/v2/score/{twitter_handle}"

    response = requests.get(url=url, headers=headers)
    
    score = response.json()
    return score


# Get top20 followers - ranked by TweetScout score
def tweet_scout_get_top_followers(twitter_handle):
    # response is a list of dictionaries with followers details

    headers={'Accept': "application/json",'ApiKey': TWEET_SCOUT_KEY}
    url = f"https://api.tweetscout.io/v2/top-followers/{twitter_handle}"

    response = requests.get(url=url, headers=headers)
    
    score = response.json()
    return score


# Get info about the user
def tweet_scout_get_user_info(twitter_handle):
    # dictionary response with these keys: {'id', 'name', 'screen_name', 'description', 'followers_count', 'friends_count', 'register_date', 'tweets_count', 'banner', 'verified', 'avatar', 'can_dm'}

    headers={'Accept': "application/json",'ApiKey': TWEET_SCOUT_KEY}
    url = f"https://api.tweetscout.io/v2/info/{twitter_handle}"

    response = requests.get(url=url, headers=headers)
    
    user_info = response.json()
    return user_info


# Get the "Chance of Cabal Coin" and Fake Volume from GateKept
async def gatekept_data(token_mint, timeout=120_000, headless=False):

    async with async_playwright() as p:
       
       # Launch browser in headless mode
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        
        # Apply stealth to the page
        # await stealth_async(page)
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
            logger.error("GateKept timeout occurred:")
            return None, None
        
        except Exception as e:
            logger.error("GateKept other error occurred:")
            return None, None

        finally:
            # Ensure the browser is always closed
            await browser.close()


async def coingecko_scraper(token_mint, timeout=120_000, headless=False):

    async with async_playwright() as p:
       
       # Launch browser in headless mode
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        
        # Apply stealth to the page
        # await stealth_async(page)
        await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"}) # -> set custom headers to mimick normal browser

        # try:
        # Go to GateKept
        await page.goto(f"https://www.geckoterminal.com/solana/pools/{token_mint}", wait_until="networkidle")
        await asyncio.sleep(5)

        # value = await page.locator("span.number-2.text-gray-400").inner_text()
        # value = await page.locator("xpath=/html/body/div[1]/div/main/div[2]/div[1]/div[2]/div[6]/div[2]/div[1]/ul/li[2]/div[2]/span").inner_text()
        # print("Value:", value)


        # await page.wait_for_selector("#__next > div > main > div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4.md\\:gap-y-0.md\\:px-4 > div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden.md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0.w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > div.hidden.flex-col.gap-2.md\\:flex > div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > div.flex-col.gap-y-3.flex > div:nth-child(1) > ul > li:nth-child(2) > div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span", timeout=10000)
        # value = await page.locator("#__next > div > main > div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4.md\\:gap-y-0.md\\:px-4 > div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden.md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0.w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > div.hidden.flex-col.gap-2.md\\:flex > div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > div.flex-col.gap-y-3.flex > div:nth-child(1) > ul > li:nth-child(2) > div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span").inner_text()
        # print("Value:", value)

        # shadow_host = page.locator("css=selector-for-shadow-host")
        # shadow_root = await shadow_host.evaluate_handle("host => host.shadowRoot")
        # value = await shadow_root.eval_on_selector("span.text-gray-400", "el => el.textContent")


        # # value = await page.locator("span.text-gray-400").inner_text()
        # # value = await page.locator("ul li:nth-child(2) span").inner_text()
        # print("Value:", value)

        await page.wait_for_selector("css=#__next > div > main > div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4.md\\:gap-y-0.md\\:px-4 > div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden.md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0.w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > div.hidden.flex-col.gap-2.md\\:flex > div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3")
        value = await page.locator("css=#__next > div > main > div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4.md\\:gap-y-0.md\\:px-4 > div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden.md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0.w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > div.hidden.flex-col.gap-2.md\\:flex > div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > div.flex-col.gap-y-3.flex span.text-gray-400").inner_text()
        print(value)

        # except TimeoutError as e:
        #     logger.error("GateKept timeout occurred:")
        #     return None, None
        
        # except Exception as e:
        #     logger.error("GateKept other error occurred:")
        #     return None, None

        # finally:
        #     # Ensure the browser is always closed
        #     await browser.close()


# if __name__ == "__main__":
#     token_address = "43xqhxrE88jgKRvXJm1XmZ7bgyXCKHhq1R3NR8V1pump"
#     result = asyncio.run(coingecko_scraper(token_address))

import requests
from bs4 import BeautifulSoup
import pandas as pd

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0"
}

base_url = "https://www.geckoterminal.com/solana/pools/ikJKfdnnJWfoqm7ZW8ovdsQsW2hXCf9fXv4RCWx7UuB"
tables = []

# for i in range(1,4):
#     params = {
#         "page": i
#     }

response = requests.get(url=base_url, headers=headers)#, params=params)
soup = BeautifulSoup(response.content, "html.parser")


# Assuming the HTML content is stored in the variable `html_content`
# soup = BeautifulSoup(html_content, "html.parser")

# Example: Locate the "Bundled Buy %" element
# bundled_buy = soup.find_all("span", class_="number-2 text-gray-400")  # Adjust class names if different
# print(bundled_buy)
# if bundled_buy:
#     bundled_buy_value = bundled_buy.text.strip()
#     print("Bundled Buy %:", bundled_buy_value)
# else:
#     print("Bundled Buy % element not found")
# import requests
# from bs4 import BeautifulSoup

# # Let's say you want to scrape the homepage (as an example)
# url = "https://www.coingecko.com/"
# headers = {
#     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
# }
# response = requests.get(url, headers=headers)
# soup = BeautifulSoup(response.text, "html.parser")

# # Example: Retrieve the names of some trending coins from the homepage
# trending_section = soup.find("table", {"id": "gecko-table-all"})
# if trending_section:
#     rows = trending_section.find_all("tr")
#     for row in rows[1:]:  # skipping the header row
#         coin_name = row.find("a", {"class": "tw-hidden lg:tw-flex font-bold tw-items-center tw-justify-between"})
#         if coin_name:
#             print(coin_name.text.strip())

# from playwright.sync_api import sync_playwright

# def get_bundled_buy_percentage():
#     url = "https://www.geckoterminal.com/solana/pools/ikJKfdnnJWfoqm7ZW8ovdsQsW2hXCf9fXv4RCWx7UuB"
#     css_selector = "#__next > div > main > div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4.md\\:gap-y-0.md\\:px-4 > div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden.md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0.w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > div.hidden.flex-col.gap-2.md\\:flex > div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > div.flex-col.gap-y-3.flex > div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > ul > li:nth-child(2) > div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span"

#     with sync_playwright() as p:
#         # 1. Launch browser (headless=True means no visible window)
#         browser = p.chromium.launch(headless=False, timeout=60000)
#         page = browser.new_page()

#         # 2. Go to the target URL
#         page.goto(url)

#         # 3. Wait for the element to appear (Playwright’s default timeout is 30s)
#         page.wait_for_selector(css_selector)

#         # 4. Grab the text content from the element
#         bundled_buy_percent = page.locator(css_selector).inner_text()
#         print("Bundled Buy %:", bundled_buy_percent)

#         # 5. Cleanup
#         browser.close()

# if __name__ == "__main__":
#     get_bundled_buy_percentage()

# import asyncio
# from playwright.async_api import async_playwright

# async def get_bundled_buy_percentage(pool_id: str, headless: bool):
#     url = f"https://www.geckoterminal.com/solana/pools/{pool_id}"
#     css_selector = (
#         "#__next > div > main > "
#         "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
#         "md\\:gap-y-0.md\\:px-4 > "
#         "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
#         "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
#         "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
#         "div.hidden.flex-col.gap-2.md\\:flex > "
#         "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
#         "div.flex-col.gap-y-3.flex > "
#         "div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > "
#         "ul > li:nth-child(2) > "
#         "div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span"
#     )

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(headless=headless)
#         page = await browser.new_page()

#         await page.goto(url)
#         await page.wait_for_selector(css_selector)

#         # Use nth(0) to select the first matching element
#         locator = page.locator(css_selector).nth(0)  
#         bundled_buy_percent = await locator.inner_text()

#         # print("Bundled Buy %:", bundled_buy_percent)

#         await browser.close()
#         return bundled_buy_percent


# import asyncio
# from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# async def get_bundled_buy_percentage(pool_id: str):
#     url = f"https://www.geckoterminal.com/solana/pools/{pool_id}"
#     css_selector = (
#         "#__next > div > main > "
#         "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
#         "md\\:gap-y-0.md\\:px-4 > "
#         "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
#         "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
#         "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
#         "div.hidden.flex-col.gap-2.md\\:flex > "
#         "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
#         "div.flex-col.gap-y-3.flex > "
#         "div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > "
#         "ul > li:nth-child(2) > "
#         "div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span"
#     )

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(headless=False)
#         page = await browser.new_page()
        
#         # Optionally set default timeouts (in milliseconds)
#         page.set_default_timeout(30000)  # 30 seconds for any locator/page operations
#         page.set_default_navigation_timeout(30000)  # 30 seconds for page.goto/navigation

#         try:
#             await page.goto(url)

#             # Increase (or override) the timeout for this specific wait call to 20 seconds
#             await page.wait_for_selector(css_selector, timeout=20000)
            
#             # Using .nth(0) to handle the strict mode violation
#             locator = page.locator(css_selector).nth(0)
#             bundled_buy_percent = await locator.inner_text()
            
#             print(f"Bundled Buy % for {pool_id}:", bundled_buy_percent)
#             return bundled_buy_percent

#         except PlaywrightTimeoutError:
#             # Handle the timeout gracefully here
#             print(f"Timed out waiting for the selector on pool {pool_id}")
#             return None

#         finally:
#             await browser.close()


# if __name__ == "__main__":
#     asyncio.run(get_bundled_buy_percentage("3ntvj3uiKBg93PKgPn37Wbs9d7YFdJ4KKHTxqPidtrC9"))


# import asyncio
# from playwright.async_api import async_playwright, expect, TimeoutError as PlaywrightTimeoutError
# from playwright_stealth import stealth_async

# async def get_gecko_terminal_data(pool_id: str):
#     """
#     Fetches two data points from GeckoTerminal for a given Solana pool:
#       1) 'Bundled Buy %' (li:nth-child(2) -> .nth(0))
#       2) 'Creator's Token Launches' (li:nth-child(5) -> .nth(0))

#     Returns a dict with 'bundled_buy_percent' and 'creator_token_launches'.
#     If a timeout occurs, returns None for that value.
#     """
#     url = f"https://www.geckoterminal.com/solana/pools/{pool_id}"

#     # CSS Selectors for the two data points
#     bundled_buy_selector = (
#         "#__next > div > main > "
#         "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
#         "md\\:gap-y-0.md\\:px-4 > "
#         "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
#         "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
#         "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
#         "div.hidden.flex-col.gap-2.md\\:flex > "
#         "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
#         "div.flex-col.gap-y-3.flex > "
#         "div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > "
#         "ul > li:nth-child(2) > "
#         "div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span"
#     )
#     creator_token_launches_selector = (
#         "#__next > div > main > "
#         "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
#         "md\\:gap-y-0.md\\:px-4 > "
#         "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
#         "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
#         "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
#         "div.hidden.flex-col.gap-2.md\\:flex > "
#         "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
#         "div.flex-col.gap-y-3.flex > "
#         "div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > "
#         "ul > li:nth-child(5) > "
#         "div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span"
#     )

#     async with async_playwright() as p:
#         # browser = await p.chromium.launch(headless=False)
#         # page = await browser.new_page()

#         browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
#         # browser = await p.chromium.launch(channel="chrome", headless=True)
#         # browser = await p.webkit.launch(headless=True)

#         context = await browser.new_context(
#             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#                     "AppleWebKit/537.36 (KHTML, like Gecko) "
#                     "Chrome/114.0.5735.110 Safari/537.36"
#         )
#         page = await context.new_page()

#         # Optionally set default timeouts (milliseconds)
#         page.set_default_timeout(60000)  
#         page.set_default_navigation_timeout(60000)  

#         try:
#             await page.goto(url)
#             # await expect(page.locator(your_selector)).to_have_text(re.compile(r"%$"), timeout=60000)

#             # Wait for the first data point
#             try:
#                 await page.wait_for_selector(bundled_buy_selector, timeout=20000)
#                 bundled_buy_percent = await page.locator(bundled_buy_selector).nth(0).inner_text()
#             except PlaywrightTimeoutError:
#                 print(f"[{pool_id}] Timed out waiting for Bundled Buy % selector.")
#                 bundled_buy_percent = None

#             # Wait for the second data point
#             try:
#                 await page.wait_for_selector(creator_token_launches_selector, timeout=20000)
#                 creator_token_launches = await page.locator(creator_token_launches_selector).nth(0).inner_text()
#             except PlaywrightTimeoutError:
#                 print(f"[{pool_id}] Timed out waiting for Creator's Token Launches selector.")
#                 creator_token_launches = None

#             print(f"Pool {pool_id} - Bundled Buy %: {bundled_buy_percent}, "
#                   f"Creator Token Launches: {creator_token_launches}")

#             return {
#                 "bundled_buy_percent": bundled_buy_percent,
#                 "creator_token_launches": creator_token_launches
#             }

#         finally:
#             await browser.close()

import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_async

async def get_gecko_terminal_data(pool_id: str):
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
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/114.0.5735.110 Safari/537.36"
        )
        page = await context.new_page()

        # Optionally set default timeouts (milliseconds)
        page.set_default_timeout(60000)
        page.set_default_navigation_timeout(60000)

        try:
            # Navigate to the page
            await page.goto(url)

            # BUNDLED BUY %
            try:
                await page.wait_for_selector(bundled_buy_selector, timeout=60000)
                bundled_buy_percent = await page.locator(bundled_buy_selector).nth(0).inner_text()
            except PlaywrightTimeoutError:
                print(f"[{pool_id}] Timed out waiting for Bundled Buy % selector.")
                bundled_buy_percent = None

            # CREATOR TOKEN LAUNCHES
            try:
                await page.wait_for_selector(creator_token_launches_selector, timeout=60000)
                creator_token_launches = await page.locator(creator_token_launches_selector).nth(0).inner_text()
            except PlaywrightTimeoutError:
                print(f"[{pool_id}] Timed out waiting for Creator's Token Launches selector.")
                creator_token_launches = None


            
       






            print(
                f"Pool {pool_id}\n"
                f"  Bundled Buy %: {bundled_buy_percent}\n"
                f"  Creator Token Launches: {creator_token_launches}\n"
            )

            # return {
            #     "bundled_buy_percent": bundled_buy_percent,
            #     "creator_token_launches": creator_token_launches,
            #     "coingecko_score": coingecko_score,
            # }

        finally:
            await browser.close()


# import asyncio
# import re
# from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# async def get_gecko_terminal_data(pool_id: str):
#     """
#     Fetches several data points from GeckoTerminal for a given Solana pool:
#       1) 'Bundled Buy %' (li:nth-child(2))
#       2) 'Creator's Token Launches' (li:nth-child(5))
#       3) 'CoinGecko Score'
#       4) 'CoinGecko Info Rating'
#       5) 'CoinGecko Holders Rating'
#       6) 'CoinGecko Transactions Rating'
#       7) 'CoinGecko Creation Rating'

#     Returns a dict with all fields as keys; None if a specific field times out.
#     """
#     url = f"https://www.geckoterminal.com/solana/pools/{pool_id}"

#     # --- Existing selectors ---
#     bundled_buy_selector = (
#         "#__next > div > main > "
#         "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
#         "md\\:gap-y-0.md\\:px-4 > "
#         "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
#         "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
#         "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
#         "div.hidden.flex-col.gap-2.md\\:flex > "
#         "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
#         "div.flex-col.gap-y-3.flex > "
#         "div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > "
#         "ul > li:nth-child(2) > "
#         "div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span"
#     )
#     creator_token_launches_selector = (
#         "#__next > div > main > "
#         "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
#         "md\\:gap-y-0.md\\:px-4 > "
#         "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
#         "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
#         "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
#         "div.hidden.flex-col.gap-2.md\\:flex > "
#         "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
#         "div.flex-col.gap-y-3.flex > "
#         "div.flex.scroll-mt-40.flex-col.gap-y-2.sm\\:scroll-mt-24 > "
#         "ul > li:nth-child(5) > "
#         "div.ml-auto.flex.shrink-0.items-center.gap-1.truncate.pl-2 > span"
#     )
#     coingecko_info_rating_selector = (
#         "#__next > div > main > "
#         "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
#         "md\\:gap-y-0.md\\:px-4 > "
#         "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
#         "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
#         "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
#         "div.hidden.flex-col.gap-2.md\\:flex > "
#         "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
#         "div.flex.scroll-mt-40.flex-col.space-y-3.sm\\:scroll-mt-24 > "
#         "div.grid.grid-cols-2.gap-x-5 > div:nth-child(2) > div:nth-child(2) > div > span.text-sell"
#     )
#     coingecko_holders_rating_selector = (
#         "#__next > div > main > "
#         "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
#         "md\\:gap-y-0.md\\:px-4 > "
#         "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
#         "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
#         "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
#         "div.hidden.flex-col.gap-2.md\\:flex > "
#         "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
#         "div.flex.scroll-mt-40.flex-col.space-y-3.sm\\:scroll-mt-24 > "
#         "div.grid.grid-cols-2.gap-x-5 > div:nth-child(2) > div:nth-child(3) > div > span.text-sell"
#     )
#     coingecko_transactions_rating_selector = (
#         "#__next > div > main > "
#         "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
#         "md\\:gap-y-0.md\\:px-4 > "
#         "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
#         "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
#         "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
#         "div.hidden.flex-col.gap-2.md\\:flex > "
#         "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
#         "div.flex.scroll-mt-40.flex-col.space-y-3.sm\\:scroll-mt-24 > "
#         "div.grid.grid-cols-2.gap-x-5 > div:nth-child(1) > div:nth-child(3) > div > span.text-sell"
#     )
#     coingecko_creation_rating_selector = (
#         "#__next > div > main > "
#         "div.flex.w-full.flex-col.gap-y-2.md\\:flex-row.md\\:gap-x-4."
#         "md\\:gap-y-0.md\\:px-4 > "
#         "div.scrollbar-thin.flex.flex-col.md\\:overflow-x-hidden."
#         "md\\:overflow-y-hidden.gap-2.px-4.pt-4.md\\:px-0."
#         "w-full.shrink-0.md\\:max-w-\\[22\\.5rem\\] > "
#         "div.hidden.flex-col.gap-2.md\\:flex > "
#         "div.rounded.border.border-gray-800.p-4.flex.flex-col.gap-y-3 > "
#         "div.flex.scroll-mt-40.flex-col.space-y-3.sm\\:scroll-mt-24 > "
#         "div.grid.grid-cols-2.gap-x-5 > div:nth-child(1) > div:nth-child(4) > div > span.text-sell"
#     )

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(
#             headless=True,
#             args=["--disable-blink-features=AutomationControlled"]
#         )
#         context = await browser.new_context(
#             user_agent=(
#                 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#                 "AppleWebKit/537.36 (KHTML, like Gecko) "
#                 "Chrome/114.0.5735.110 Safari/537.36"
#             )
#         )
#         page = await context.new_page()

#         # Increase timeouts
#         page.set_default_timeout(60000)
#         page.set_default_navigation_timeout(60000)

#         # Helper function to wait + get text from a single selector
#         async def fetch_text(selector_name, selector_css, timeout=20000):
#             try:
#                 await page.wait_for_selector(selector_css, timeout=timeout)
#                 return await page.locator(selector_css).nth(0).inner_text()
#             except PlaywrightTimeoutError:
#                 print(f"[{pool_id}] Timed out waiting for {selector_name}")
#                 return None

#         try:
#             # Go to the page
#             await page.goto(url)
            
#             # Fetch the data points
#             bundled_buy_percent = await fetch_text("Bundled Buy % selector", bundled_buy_selector)
#             creator_token_launches = await fetch_text("Creator's Token Launches selector", creator_token_launches_selector)

#             coingecko_info_rating = await fetch_text("CoinGecko Info Rating selector", coingecko_info_rating_selector)
#             coingecko_holders_rating = await fetch_text("CoinGecko Holders Rating selector", coingecko_holders_rating_selector)
#             coingecko_transactions_rating = await fetch_text("CoinGecko Transactions Rating selector", coingecko_transactions_rating_selector)
#             coingecko_creation_rating = await fetch_text("CoinGecko Creation Rating selector", coingecko_creation_rating_selector)

#             print(
#                 f"Pool {pool_id}\n"
#                 f"  Bundled Buy %: {bundled_buy_percent}\n"
#                 f"  Creator Token Launches: {creator_token_launches}\n"
#                 f"  CoinGecko Info Rating: {coingecko_info_rating}\n"
#                 f"  CoinGecko Holders Rating: {coingecko_holders_rating}\n"
#                 f"  CoinGecko Transactions Rating: {coingecko_transactions_rating}\n"
#                 f"  CoinGecko Creation Rating: {coingecko_creation_rating}\n"
#             )

#             return {
#                 "bundled_buy_percent": bundled_buy_percent,
#                 "creator_token_launches": creator_token_launches,
#                 "coingecko_info_rating": coingecko_info_rating,
#                 "coingecko_holders_rating": coingecko_holders_rating,
#                 "coingecko_transactions_rating": coingecko_transactions_rating,
#                 "coingecko_creation_rating": coingecko_creation_rating,
#             }

#         finally:
#             await browser.close()


if __name__ == "__main__":
    # Example usage
    asyncio.run(get_gecko_terminal_data("3ntvj3uiKBg93PKgPn37Wbs9d7YFdJ4KKHTxqPidtrC9"))


