import asyncio
import csv
import time
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# If you don't have a logger set up, you can quickly configure one:
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Example get_gecko_terminal_data function (as you provided).
# Ensure you have your exact version (with your selectors) included here or imported.
def get_gecko_terminal_data(pool_id: str, headless=True, timeout=30000):
    """
    Fetches data from GeckoTerminal for a given Solana pool_id:
      - 'Bundled Buy %'
      - 'Creator's Token Launches'
    Returns a dict with:
      {"bundled_buy_percent": str or None,
       "creator_token_launches": str or None}
    """
    url = f"https://www.geckoterminal.com/solana/pools/{pool_id}"

    # CSS selectors (truncated here for brevity) ...
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

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/114.0.5735.110 Safari/537.36"
            )
        )
        page = context.new_page()

        # Playwright uses milliseconds for timeouts
        page.set_default_timeout(timeout)
        page.set_default_navigation_timeout(timeout)

        try:
            page.goto(url, timeout=timeout)

            # Attempt to scrape Bundled Buy %
            try:
                page.wait_for_selector(bundled_buy_selector, timeout=timeout)
                bundled_buy_percent = page.locator(bundled_buy_selector).nth(0).inner_text()
            except PlaywrightTimeoutError:
                logger.error(f"[{pool_id}] Timed out for Bundled Buy % selector")
                bundled_buy_percent = None

            # Attempt to scrape Creator's Token Launches
            try:
                page.wait_for_selector(creator_token_launches_selector, timeout=timeout)
                creator_token_launches = page.locator(creator_token_launches_selector).nth(0).inner_text()
            except PlaywrightTimeoutError:
                logger.error(f"[{pool_id}] Timed out for Creator's Token Launches selector")
                creator_token_launches = None

            return {
                "bundled_buy_percent": bundled_buy_percent,
                "creator_token_launches": creator_token_launches
            }

        except PlaywrightTimeoutError:
            logger.error(f"[{pool_id}] Overall timeout error on CoinGecko")
            return {"bundled_buy_percent": None, "creator_token_launches": None}

        except Exception as e:
            logger.error(f"[{pool_id}] CoinGecko scraper error: {e}")
            return {"bundled_buy_percent": None, "creator_token_launches": None}

        finally:
            browser.close()


def main():
    # List of pair addresses (paste your entire list here)
    pool_ids = [
        '2nXMJozq1dJDmgYkiKd4davvZpJMjiBvrkBXtuxwAvPN',
        'xAwVLm6erJtNqLXH1mzfR4deoebXaREt2r4qR5ArFbd',
        'CQh8g6jRL3kzygi5TWyBMxghfAmCTgQw9q7jK3d87okf',
        '64UK2W6wSGc1BYZQtDLtVuwZv9UxbrZbpfFMTganY1bs',
        'JBAqbFVfpeMR2ajkVRzjsWWyq9e9HTp6Qy7P826ep7sv',
        'SsVsdzq3uHfbTGf84GEYgpGQwi2L9YnqMiXsjkK41Df',
        'FJdr9JtbUdbi1tegLnxtWsLtz6mukWsXGCtc5ztdSU3s',
        '3FyyuWjxTTeRsSSkyEyWGbZ9u1yDHuXQrRsAQqPTTaX2',
        'EtRa1ECAyYctwjKEa9rGJ27w96kUXEyiiwVumBZ7d55A',
        'C3TxRzjYD9m2kRZdsp3NAuashc4JkpCFQiK4KEoNd4dX',
        'BS6ivaWqwQrwxJpHKoTMxVDQ74SDVqmZwN1BR2mqAJTu',
        'ECDsZP8UaHS69WNvNGL9Jymhxpez7ya5APQ1AKa36mhj',
        '2UbJd3DTydnFGi8TBtHyL7rDncAhbrGwNnwg5FVKmKXA',
        '8n389vyrH7rwFR5bE2pP3a27qa3vrhezHZYjJ1994ua5',
        'A8kYykiHrbChD1peWkEKuQ7Aer5hjFaEXnQrK47Fz2om',
        'HNZSGZowQe2Y2kk9swiSbU1NeGncgVs8D2ch1bWUsNrS',
        '4kC8CLZQe5UfCh99xAzL1LAdJH4ZvYvkMvgcuuN49EY9',
        '38QqJiTm4nFhpFvPUv1xqb5iaz5A1dfhcXLiPJw3qJVk',
        '3dNx8XTNuG6hCtfrASEpF3E2GrN7pMUH4KetfoGTC68t',
        'FtgD6b1ZpKo1siFaXeSBp9QmhLtTGaY189wA6exV2YBm',
        'BciK3xb4avhBc9BsH7czZviNwMAwmv56kBwhmbvBgQhX',
        'EfxPLHUkW6ujgZsieVmcSnET3xs9VUV5ekVcssDCqjDm',
        'GTfpU2SJZEmKw3gU8pyeiUdpuuPt1uPoXCWyhekq92ta',
        '49VDdKgEfF67rbeRA3jJdmKv77MVHEmzwcS1Xbj5CMxN',
        'EggttpKs4foTwGLTaJv1ML4ghGDo3URBiAH5GgbLAJmY',
        '9H3hoVcLCAtGdemGubjJAH353nqYmuSiYyU7skBEHuLj',
        '6QX1BBXwi1CGQeeapLYZLxoqE6oRNo7NHJTyDGWwq9ne',
        'FUdCpAEjFop7t2niND8phzechQ64vJPBAyWoSiFfdwYs',
        '6Y7KXpeNfjmPoLuto96f3sju9Wf2XkNY5GUhuTrYm33i',
        '9mxRfPjqSDoP2W15Rr8RDBiaawSqgAdb1xfSdPWoVuAg',
        '5p46iwPZo1UQWqqyGsBwG6WQQfGjS8J8SLuKWzDMHTAv',
        'G51J1k8riEsemXjBKFStVQRA11JZrtPbw5hLCdx2RM5c',
        'BxxQUcvax9PeeMWD98CJkektMa6m8YZ57tL9aH93xYj3',
        '8pog2dB3LqniBU5aewwZS2NTFDyR7PN3nYsnFoDu6MWw',
        'DA7wXj5Ue3afENEp2yUJbtXYjrvFmJMPs1EfT6wC6PYW',
        '6HoVk86jxAfqVU7dWVF8ZyHGkoBCQKY87H9QS74UAv3',
        '2TWKdZcpRUaR58W2ucxDn54g5jBDZ66i2WfXzdPC49P3',
        '2aVGxUDAsiH8ceKT1rgJHCVEvgX7YxMxmwXzHfRW7zE3',
        '6qy1vUM79GCZh831Xf5Ym9D9pTa6DhepchHd7DVjkAG4',
        '8HhJonxCcDiivP6rNxNR7nYecTDFFEWfWDMvya61tKQ4',
        'CiPUsUFJTkETwTVfcA1rk6Vze5XpApyzCLsfHfCjYdAu',
        'ATa1VBQ5Vdbt5yPRswTFscE1d7tko3vHwEXRNaoYhpS5',
        '84BpJjGkJkZU2hZTFNLmgLitJoSfGZQiDMtx1ZFCoxiy',
        'AN7ys6tXjx78iPUv9R5YZC1n8jGRxrbwWJ9Jox1w8Btg',
        '7VUCv7J9XJ3jyuDvsBCrJCzCCy7KcnJwEzQHwjjsCKGH',
        'BXQAwZc9nWE6ny58dAam1eFcXm2ag3nwGQZeEjTJdDBT',
        '7RSGBjZCgLLYSPDs6EUL3AZofQjRgKU7bJ7DQEvaeSf8',
        '6iwsc9PjUgAJKA3fTmBH8WYRPHo4a8N6MaPkNSpWi47E',
        '9Ri1pHK8ApboiefX1v6miyJRKWiEa1RtbYmamaKH4DMD',
        'C5S6pmaPjuPLwfRaKWnfH9thQ2ZQhSYSkpxh4QJW2QYn',
        '1zvVg9Pg6BbNvBGL6xpqP6Wd4Vw35VX1rhXXxP9fiUL',
        'ERF8febVJqmrPx6b8j6zLjmN6xAEk8fimKDSLyEosFYK',
        '5spTSTytMdp2ZTEcHUgzYGjAwtRYJLDL44dyVvGTA62F',
        '6JAFJ5yXxCuUa4DC1QQNNCMfhcRNQHGoP1th9UZ7aYFi',
        'FcNMnuScU7rVRGqPAkx92bSmGxMGsnXvBbGdfzLRB6Kg',
        '7tPwhZKvzq2xhy6RC6fgJeZXEZJrX5bs98BJvhE7NVJs',
        'E5qP99R7iUvgtHyjetaMwWCfFnpXo928eBaxJKauZByq',
        '48L3BzTsLtHf21AxKXmSvteRaM6LRTMnSc6xNw5JYTfE',
        'gcrXUNEoom8AMrZTmoAYBaA1qLcE6ww7yJpPYjvF3Ce',
        'AisnXgyrpSLyAHeShAjE1a665Ff8fjXBgEaRtu21y7T4',
        '2g15kXK1yF5VaBb98N1fYEAZasGCh3sMdTdyuRjWG4Ee',
        'HUcCTB9iX7pz4HFyrGTZo4E8KQzCxxRbbdoYQvr2mY8u',
        'EZ8Bn6hKauSQSr8nZvxzhFfe4PR4GFNVejjyum2a1rcH',
        'VPkVM88vE3RWzfMveMV2tk3Ae5G14hndqFwFNQKBNQb',
        'HJsfyLGpyQQH7eXd8PJzjtfK4bm7YdYyvZH3pRfL1E4z',
        'Cd6YJYXdpEV7x8PgPdqvCBfsw17rNj7VWvEYcQNyeD9j',
        'CZky93zYHxQNyGD2jAzkPVTeVHjduQHHJhY3Ba3uTNwp',
        'Aymya2gbtE4iBwUxNYhX8G7mSgu3Fpax6yC6kkJUF7p6',
        'DuTtzUud3nFyeTMkJsJZQtxfNJrUyHXs2oLZRMRBoLUY',
        '6g7rMd3fLrgjFT9WtoRpaAznYMLooMg9iCBX3AvhwEtL',
        '2VQTxiaL1jyVJ4fhwLiqRDr5ynrQmc9CHoAu92JzAycK',
        '5E3KEzirGVrQAqPuSfoWUuc42td1AHCoxKxLZdm55Wj6',
        'DQNB9K2SJy8JskDJeBzDKfgb3YdNX2W8MKppT6YgSep8',
        'Evs19Nz347ERMWebDxNfyALEmxk85HBraVskpX5CUVad',
        '8d6rKE6qaTkNVwzYj6PYk8gZd8HwTQcFhx558bg6kXo',
        '32rEWeQrE1i5UDMziggbADRPf6ybTJkgoJarURbxPwzy',
        'CwbuPkShz7Ddkwqzf5ScCr62xBUUv4g5mSwseaCrHZsa',
        'AZvf8AQCsQ77YtMBXdTgZ1SPEQmqqGMj21x8TSeB7nEK',
        '3dS5azTbBWqpfMZDdvWkyerEKWYkg4xuy9Aw7Pi1TY6N',
        '9K92zfV6tqJHWa2d4Ehc62YEDTermW9r3mmJCY6Qt15d',
        '3QYTeFjz92KKkPmH1MP7fQ959qGyiK6ikQ8N8UQ7a62o',
        'Bhsi2NGHiTWGmb3AN4w2z7bbngPumkJnBUNgY8tVSqL8',
        '98i8KXcRYFLKGF7Sgds8gakgghtgSaVQi47jjp4JPc2q',
        'GZSTRHQzWgjSuD2KWm34PFmryugwiKRfw2zjdEDbH6F3',
        '9R5MVuX8iLfhn47rF3X3T8k1aHiZ9oTPoR1UfEBkoGZs',
        '5pfbGeBWe4Er5KnT1GGSY9EXweWdpVzmSGExjfYK4DaD',
        '9NCmDPUegtT4DyzKRL9Nusw4wbB7AS8KCAPp92Nyj47Y',
        '8Bu4nwDQ1DEZJbZGdXpLKF83RA3ofy1jB5WLMX5FqbAv',
        '9pBQYeFGt9LRq4fbcPZb7gdgkpnYMwxsTc8fVcyeveQ1',
        '93X2Ng3WegKaqg9GECZaF89pS2HXyAm76gKmsQ7zdfhT',
        '999m5U9bRkuPBEqSJNRexSXPJXB5siqNkEjXfhca17mD',
        'HDSEPu5WDyjEFcquuAncU1anQiD3q2Mk3og4YDQaR9eR',
        'JCoDRD6op3CGfKFBTm8tJyUK6yLw9ERvyhrRAk82Ejhi',
        'AC7PeFZsZuBtJoqPoynqh5AXhr6KMxbVKLXidXJBxyXE',
        '9YN7mTEdbjp3q4FDsWrCubnXxqp4myDKmEyC9kc4NGFq',
        'DJpspEMhXg9uNChAazViibDueUmabx3NZeR5JT7KAZ3M',
        '7midPvQVQeo6eU9di6hX2QiVdZyqQyo4B58A9MQZc4PA',
        'BmQj2moFLx5QNWAqZnm8JUMe6HDvM6adaXQTn8M4Qdox',
        '2MMSsZ9WR8fP7dfEAptw3SL7ThZszb8a9JsnGQrStqzA',
        'FcD91aHcdXjvJQAcnDHH71p8xcYiqoJN7SuKBGWu4qiU',
        '82SyWaG8wS2AD7vU1N4UKHH2Xc9GtaVF47twxvfdnYNJ',
        'B1nXJ4X54vT8aDWDFDAHq1tzs5MbHFJbJF7EVoU4SMvk',
        '91mQiY2VPcxMEhcPDyvQH66FuynPSbatewCwFbWP7Ktu',
        '6C5kRrorCJfjRqNWiLdY1mhqqZDend6NAhyPq25oivmG',
        '4fRo7rmYDqsz1moeYKKzV4GCpaaLbAh213Tis9X7Rqmw',
        'giHzgUsvYHiw7tpGGfZTHqBCfv1QBL9P2fHmrcUG6Pm',
        '5VozCBYTRD6sy8KquuXVJP4ekGS2r2hWc9p2zVcs7xv6',
        'AzC2biVVDf3NcKhCx65uWq6K7stPaCULxyCTqPNrotLb',
        '5wAtk8GCDFDtpUyhqbi13D7K664V3QUKSQLcq3HAzFjy',
        '4e8odKCH2jkcUvTtweecQ786mLy94cwBAzrVM1gUirVT',
        '25CjwFtF7BVgX61KLUcRYU7YKeR9m2rEvJv6fxiC6qFJ',
        '77i8FqmoUyBMo3XNBf4xDUJbuyGaAsnZhX8roc9myi2e',
        'E4PJYFigosMWwygczZjxRZiESNhdkkVqrWEGr9hbz2VL',
        '7vVRUdnHcXF8AkTEwQLjPMB5y9hbX5cJVjgCyC9vcbmk',
        '9fajdUwrYSz28BNDGhykFxCbEFHSQscUzJtNyVEJEpCz',
        '6A4ukkr6R8WVNEEkBqiipgTJ81VgkBcX1pExVuaJaSGt',
        'Hfv1sL1rQ5yxUzMaeWEM9y2makad8snBb3AEsYKfefwG',
        'A4jrsiWXSs8b4roxkognPZWSRHH3gfMKTsAEX2nprDqb',
        '7eyTAUckM1btc6xuRZziwP2cXfVJEiYwWRoHHEFFLtGY',
        '3Supa21TY3xT9ivo3a9UUgGABxiTWAbiYHXwB61rBFjr',
        'B8Ag3vwnLsQMdQMDJcdY6aYXzE8praWir3pL5cNDkU8',
        'AdjQvumgxBnbysi5Mz4EEMLWvvaGEYDvUUzNeuupSc7i',
        '28dYmULqigt9RSL8NQYtA7HfuFsr91fUQo2B96mjhXME',
        '6dQrY2PimDRFwrrznybhzjGNxmHDezckaDey1A1432Bf',
        '9YcuHhSMjGnbmurSissjtqrMAFWniEtfeQ31GDsGx9VY',
        'AXsFT8319Xta2JVZQkQZVTH8snbix6M7jKVtEW69vQeC',
        'EBHzhuAQGMENvV6YVmbjGfvSBCkZ1NUYKFUaqRvctaw2',
        'DiFRNzbpQhZKg6dkufFXZ7CXjjMQEgZEbk4hX2rTxF6F',
        '67fktAwiSk3Tb1VZ2Yuya8fth68gGqHEWorQPzRpdTm8',
        '9qkVP8n4ZQZWoYKbk1QXG2oNhVdLew7rAfMXfmAtx3HB',
        'JAeT2TYzkhZaYQW3u8h6ZdGuqx2tx8XCAW6p7vpBP5NR',
        'BtBw3L8bCTMti51Dg5whxcVGGNdkHzZRcyZH7GjvgWWF',
        'EwiYZQ9Cv9NW54NAQWezeurmLN44FNYutyCcdNJYCfKv',
        '34aaFpgzriTGo6HxEcV93j38VPysR4QNTpEbKNghhe8v',
        '5FX4xjpLGTzK1JHV1Nwt3cU8hSJu9Jrj535h9GZZ7mGe',
        'FuWbKgRYhJo2pp7y2YWBqmV6qc3EJUwdCXNoTz3Jpwfp',
        'DpU6dtEnLE2cEQ7AJqEqHvrjQUQtTjQwX1hnr8dj4bqd',
        'DUeEJFUztkiuoNGDfP5n6B42dJMDTUcwfEmfPGkeH4BN',
        '313ADcxorLY19VzvJDJQZdRYkz2hdEyhJF6eqbA4Uocf',
        '7qddiBPSnCcUuExEfXmYgRRNPFp1StKo6QLWgYt9K3Cz',
        'CqZYAJ95mDJgEwxor6nzkEM9ShaR1ZQxSv8RewU8H413',
        '2PVXZ7wo1N74fdRbiQvFtYyTLKYUEvBuCpvU5BH9HrEd',
        'CPxTSzjU6TEq17YR8b5mNzpvBfQya8qDLgRe8UoiyuB9',
        '8evppTG32bdXNrgRCqhux3snfo8hgwQWwyu6e2zgDpJ7',
        'DpRKyqNNynGyXC4TyMSkU4iuu4v4prRp9viDPMi2bCvm',
        '3Yj1DMabm4jCjEP5MF49kEgKc6fQHBzMN8EtJwHhdyF3',
        'G6bb6P5LHXC3mKNmyixYJcdGmxRRxUuBtrkTLzASvP3b',
        '3MAYmgJo5b4SfB6MUA5sLDDeBGgoGboPDUeZpXu5LHCt',
        '8QEt7jNPtmUo4Bvp5V4DuqbNJM3MBbN8prFUcQ5bYMg3',
        '41JHYX2QFepfNjgiW4PZDgk3rpuVP7ndDLsUgV19a8AU',
        '7h9p7kAEPPhSdAYqHh3MtTGxeMY11CK7qSFez79xmg5V',
        'S94eWdywzLeoZV3nGfnDkdC9maaSkTfj3ztPf7x6Nbe',
        '3wyR8BDH82cshD8wzaooxnhXDaoWCAEETVLUqJeNdWcj',
        '9keekRshU7QAbmK5jGj6PhMnBpfD8iLwbLUxY8pJJpxU',
        '9ddUsDPHE7PdCR1NXJeEaeQHMcVSzPJA5SiDmnrrgntt',
        '8hF3MgsVd6BfCFkNkqPuBceWLti1AYpPx1LhQ84PMDj',
        '9UJ35XYGXy7CwbbjvJiTM8T2gNAyLXuRgTMevtCjTDfK',
        'aTmF3pjC6mvKFRdSiQUKoqoav2fSmETPDbC7z4gu5en',
        '6uZobHrPp3p21EaSvFLoebg6JpsKeWhrp4ko7bTpYrkS',
        '4EyN1RguR37Z4tjxsjc39VuXsAbUg6Fv28Y5FWVNmUva',
        'JvTNM9VZWweEU2eBYyykHUckHx1evucxNzAYA63oecw',
        'BRiMZ89EZcbECS4UEth8hirhy7YGQNbkEnUDDgCuUZPF',
        '9ShMSsfjvhtN3ZFjoREVb1MBRSPSBuVSbXxDovuCAU3B',
        '7aWGET5bRZeXN7ysNpRRpxQbf3khWzSr1H4vChAaQFDP',
        '5LYEc1ZAH6fREC3LYn2fm1F1cT2pUKsKLAaMxMo8puZM',
        'DDEDEyus8w8pwquEQ3YUS9dG434Lth8x6eqjimhZMnKE',
        '5x3HqCokyvZuYhWcLjRDVbu4SGy3wkxtZKBTY3m54eVx',
        'G1n7JTr2Aq2vmC8uAFSrDezfy14kMEBLVQ24tNALUAJs',
        'ACX4YqkGqhPhMcnTD1DvzK5GkVrBQ7iu1vFBySx5S63Q',
        'Ewaw6TdATeMo8qQkb1QMRB5t4HaZQjCnuai4XVSc9hhh',
        '64wtMFyYkS5wZ3Pq8uJkk1EsaoXb2QyEjVdgEVGeRscv',
        'FQhp8joW6mKjWNT1nQNhVrt5U48g5ZTg13JnNkYki1DB',
        '9oxgvqYXsKxAa7NMy5dM976VTVMdSvemyaa45wuANhVR',
        'DeM9ifAMsZTqNTTcJg2ixHnDtHkao58NXWADPLwxNSKL',
        'HzdYXK81ifojRJgcRBf6vxGFyEWdECfwCFhbk5hDuKxp',
        'DUBdx3KPrTv2htL1jcrYQ15ieUBnHuT9atH5QtJVFzXX',
        '76W8pzb7LqrWwUhEoXy2ViwcWt8SfXQTnZPW3FVPzEpG',
        'H3z2FDjNjauRYKWp9mKkkWfuD37pTg2yw9itcoxk5BLd',
        'CRrtiGpDYsRFGtSWX1f6PcdqZ2wTZRMHiNUSzfcR98dq',
        'GkMVPKvzpjkaQM6UKsHuFUJYoQjqkYnYpHmwXvxPrKvH',
        'EnmQ9e1Vr1cNLuHMDRafkrhGX9WiFMCo6hJJFiwzD8RF',
        'GPkxHaRLkRJtRygsjqC9RQbM7rXccMvZBugQ3TgXbx8J',
        '6wspzDgye8SbWGPRAHk1WkZGC1yJ58fymNYWE24iHi11',
        '2dJJmdAN4mUMGfc1UVZJaaAkSEAsF5un2qU9tRMY7xQR',
        '9dbPn9QGLujMVjsERcpte16CQATkmbGyk9RjeLD7KvQi',
        '2j8uKcMD133y1qiwGeJMQBzGqudrbjktXEZNCuANcKF6',
        'FPET9AF3oS5gkyS2pXPnRFj5fqW2qNgvYoQkKzH9XHyC',
        'EdAZBm711CnAzvgYsS9skweaeMVn7whmuJWCfzzFvPUj',
        'HxtqtXECRTtDZTpLJVnySDziHDf8jktjVGsPvy3eyWnk',
        '2LLeMQJbsH2cwBNYFgqGzn13tPtw812gY872YBiNffVZ',
        'BP2od34zRp1aisMCPnBvjGDQbELbLaPYPdGo8pmkKTXh',
        '2ouCt1i7FQf64G5pW57HsbbKaddPB5pkEN4zvguNy2j3',
        'uK6kxE3YA9dcnVUDswBrMSj7zV3hspzeW8BpxK5b7tJ',
        '8SVfLmHgdafdg79FrYtDpkxQMfyvQ2oXKTRBdocAVqu8',
        'FPqxYryjh6PXnzV3EpL8Pz3JYEyQ4CREUofEk3L5GXbC',
        '7pv9em5cJDPbD73eNYhpoG1jKnKK6evLAsrbuPGbXetc',
        'Coy72mKiEreZ54RwWxFC2gKqEAGRGYAjHFPbFMjFrDVa',
        'E7bSBjAJoGTN4dQDAPYLstpKfRVbMZVRGrLR9iKGHwPh',
        '72Mo3wqJB54pHwHhWn1H5kGuKqc4b5DDznSL6tazf3YD',
        'Cbrhu71g73ZriEgrYzo8iJuL9hQ8TS4ddyDLLony4Qqu',
        'Adt9E9RSE7vTW5bcQ2fmE1GMzvy8hM4taNZrDRoSYwLK',
        '4FEifz8UPmDZdzXYX5WJG1mjg3Nhi5NToJxev4K6RQND',
        '8KFQyHDUopiygTukek4nj8GQd94oGhN87PHs8tKBPRQj',
        '5EdKsAX8Mk38CoTu5NJHJw6PDJnfmxgknTdfBoe3Cbds',
        'AsU3M6WuWepk1K4NvB4AQdvLnFr6zUYcJKErwQMF8EHS',
        'AHbMCXyKyaCkE4gEpc17JMX6mYdXZziQjH9NUkYGWFAB',
        '7WNZ8m5H4dQJ3psQPA9rBZPP1FCBEPAcwMk8ySYGcdVk',
        'DYMzr7cGQnTdnDgPa2cMGSopt9rDQHLS67EBdZbtdHom',
        '8GHTLHJ6YKdrBS3dCLMMJuHc9PxoCuPEpBR7Ez8y3Kr8',
        'A9k8vrDG7oiePStSjNVNijhsDitDBMamk7ed72tJviRe',
        'HA6m1Jw9Z32jLNr12tQF4BmuG63DjWSEPvkcGmLhytMd',
        'JAJ8S7miEe3sEt8dpnsNvwMXA7cQnteRvkJnS1LxLTmb',
        'Aa9wj1FjgRmAcAin2PZCC5omrpsopJiZGbNFnv3nxd8t',
        'Hh4MQyBWbhaEVdYFWJMxi79dP7MaSjctYuxRrCHeoxTe',
        '6ftfjY8ccntqNimDT7o112tRBULxoB2oXNezPaNnsDqc',
        '4RYvHnvUhPe2JVWav25AM2FAzMRVRuLzJL78pS84vEBq',
        '4QtMqZNCyxt3sLj3yhqwe8iMJ7qatYVq5vkS4XX9ppUW',
        'F3AE4g4U8dRxGMvwhAotWr87cYDZdSFbYEth89Xd4L2w',
        '29YFhAneNZ1fpRXtZrHobFnU1Q4KTNTSJAHZWcDBErhg',
        '7iUKNCAbb9sAsD7rmXA9iBsFS7TDX9HHqvtxtZ3TwLtB',
        'C17diLwem5Mim9CNQEJ4RRsfd5qJKYYUprExpuq7qRNo',
        'FkyjBWJqdCmax3WbyPavcdAWVm5CPv733Su7peW2QvQJ',
        '4u4mcC2wLg8BEJJcqqNpuDGhitu32NdrKYLqBWhsMKjB',
        'GwLF5Ws4qUL7TKiyQBsirfXSaA8paiXdgVgfPcmRh2PZ',
        'J9skB8DfHWJarShVZNV7nnjdLZWDE2fnwGDdqkU7qFuK',
        'G9s6YAtFe6W4FU9WGKx9AcufzEbLeUUZ48WhQ5enBgZ',
        'SKbtFANL4A38q7ekm46J5dCQyMnY8UfUP1XpevmynVJ',
        'HRTvrRsLMoW2yKRBh29hhLhTjx4GTdffXLCndeEumpSF',
        'Cw5HCZk3vfVmFmb3Z4mFB7pYm1eLRbaER2DXSviz563N',
        'FDijSz2ks3Q8bSvqtKCZYFnz1aBuJhEdAaM18vEwEZeG',
        '412MJyzLwRJrg2JG5WYwVowPSPwrtmWbE3hd6XGrUzhE',
        '6YvZXMpXdzu7jWsfi8QsifqMy2HmLLqJW3a1L5bJ8zEh',
        '6Eaiozc9EPkf9ryHDgxu6hgwWEHbfjkryS6ip8kfoN1v',
        'B1wAybkfhvSJegQPyPXBqsWmsJUkePXcbgbsxfUfmmXS',
        '9ejiNV8pmJFmh6tnxT19vAPxWCG2BjKiEd5WUiRSp1GQ',
        '8LrM6ySfcs2Yg9obkbi3UJZbdeiMtAkv9K8Uigv1H9a2',
        'GsSywxWBokKrsqzmYTuUwyepsKsNaCU8QNuMmDJbUJqg',
        '4NxpPWMs3TC5YzXiF57qbbJnG634scvCDjcPZSu2QQfp',
        'CVwNnjoa18ZfB8HwbuwupfVCN7tt34V8UtumvTmEbTWX',
        '32CPhwb4FFdP8ttbd3oDNzrL6eBZigtd3VCSq6dxHcPb',
        '3iDAkZiJqrhBRKB2QNUPipRomqqZqTxDXkV6hdJ2Guq9',
        'F3RfuJXcWGWiYGFM1K3T2hzgt4e65WaWmmb5ny8Vmjaz',
        'HeWxdMa5m9L3TrjEy9DGqeW9hdEVvX5145ogn8up3Az3',
        '73AeJW55Shgc5E6KFKo293NBhhRhA6FXxvCK1YXzz9pT',
        'GRMMrGtXgbWMXAXzTgeEVYFzJxGaFskoqG8mtkKJXxCD',
        '63P1yDhFx9EjuE61LVDEmTnPkvh3u7m2DCUcxn477wGq',
        '29EPtg6nfbE7srPPi28C4G3ARnhf7bdsffraaEnQ3XgV',
        'z2pngHmUvW4HJknWzhPVzhYABA3unBLFs9apV2a2SfV',
        'AqoYBf4t3MDK6HDkQ44DBdsPSMLNPv3P6yojZzvRY9jR',
        '6urvbDQ6MHtLKieDtSs8Zt3iKk7p5pXZA9eZcJupSNqq',
        '3JXC4uDv7zr9nhspA1987ojH7dapbNGJZVfECMtqrki4',
        '6TUbMuzFovMRi9iSLq4c6MPYEZzdpCWfitUqfenvURdt',
        '9wkUsFM4Le49Wm9bnQUYEVQrW6fhBhqEoxgWttW9mqQV',
        'ESZatwnPy3HMJaABT6cwRn7W2VzeC2urPr23ofc8L7KD',
        '8f93uvHcbrJ1S2b76kyKK6m8AuDQBMy8eMDtmVXJ4Wkp',
        '3Y7Dk3FMwm2kHsW9cK9on3Ai6PQGxvAfEWqLzq6afGrW',
        'Dpcg17ieajz8zgBVdSX1qJWVsq7bGtJQroaYRXfWXFnU',
        '7Foobp3g7aSJHj8V1NsZvaUneq2pPRHu6oB2Lyxcj3Xk',
        'FcMpvmcyQs1V44b7hYQT3BZvKV6DvZK19uEX3UXDLoDE',
        '3uEM5iHzKnQvUrVXkWmGsjMSsHtH5TuyCuPJT6aDmGa9',
        'FgP61Wv926AtjVWaxBAwdSc9Q3o62XqoTKhYiCd6yWXZ',
        'F5XrGN7YFegEd3ZLKzP9ysr3PoiVNY1XeGM32iM9oMA8',
        'DBBeRtKNx51kQm3X1deQUbgrY9uMBBx4rQb1kzk7oBMH',
        '6okNGjxV6t6zTHLTU2DmFQt6zhBb5WvjXwqQtUWt2cdU',
        '4hkBvMNhfCqboati3kbD4H5rE4b3k1XhbRnbLbSs9W7N',
        '56shjcJVLEB9BbHCBHrKr9z6wUFztGddTWFgSY7EYR1t',
        '6nvQSJtva728V8GNXYJEz3Hi21Sts5hD5qWoZnWFE7BL',
        '5txmPEbts32XxqhjQLPyNomyU1CcBJ39Ggn34kKdUHV1',
        'CVe1oG7brnNtwKiF6kSoNVLjasesrk1jSnM86vRYJmYM',
        '8ctUVHMxYX1hJSbXhmVfUV1qcZZNk36mrnpecBkuEokr',
        'hSvoFyDhDs4Ufqq991h3ZspRibGHy1pBBFVnf9oERCL',
        'HBv8uoftmocVgwFJsHm3hNmbhDqAmn3FCvzxYKp3dDgN',
        'FtAMMJoQv6wsyyirQAMLrEA5LCCvzbQLfyNQxB8JhdvB',
        '6mBHo7rukF2YJZvh5QeMPwz2StSdWtcAqk67VFpfQbTK',
        'EYqnYgzBevtKhCEeiyxzYwiHWnMZEierQunroevrrDqa',
        'Bv4412BPpzx6wimrX3pfvGSanY41Coga5TfxF8TgYCXV',
        '7A7nTHoN4zXhDGipXAqU6WPiJiAMRM8bjUg5ZGCVFf2u',
        'A8SMPWoKQTmZV9pXNa1P5kAPoq733Pu4aC9iYWuqKHAs',
        'ErguS7skguFXayBpArWFMmTYvjnVKDszCvU5Vup5gZYH',
        'ERgqcD7JVEdeG98X8dfr6Wo55rpKuTh2VEGaBDdi37TV',
        'AhaJdhdyNXXJ8geERWGmdRWAFx6NPKq9CucvtRczwQcc',
        'BoemKFP1fTED1qJdMDERKVZ8Fe5FnweZDEeaA3rcDbPE',
        '5JXEAxVNM7Z9CvKKj1ZtLP1si4xydPmANFSeXu9N8Ncg',
        'CFijSdFCymgvudhGPUnsoS4BYa3znaWSng5uhsVWutrc',
        '5rT7wEK7s5TxijMpwuehnF9oPHEJkwxTtTHQspWx1miB',
        '9YeWK5s7VbQdUgLjgGJRnscApgGLEiVUEeJsUY7qLWGz',
        '6hUFHZ8vts3dFbw5poHHkpqtmcn1nJUdbc8SDFFC3j96',
        '4R7EftziFrJNewB6uK1aGgxqnwaimTaur1yJz7RqBXZb',
        'J1bZgProcDRvbXgHYQU3ZZFwu5axsgfnSaoLJS9CNMgZ',
        'GNmhNoYqucnc9kz5TwEGJVDWpu2JBcUWkZBEmDFDJnX7',
        '7CdjACKreXhvtVreQ6adpjirWvtjYP1JBXX3W5TRk5P8',
        'BhHhC29FsawSA9tnVsvfawyLc4rDJUx2ctc2NuXGAzQc',
        'A9RwMdKD7aG3dkdoQrvFgkKTuTNiqHbvt3Jw7uuEZe8u',
        '7mWyjoVZguVApj57JoxrLDTw24dKMg6KP6ZHGPXnF8Et',
        '5UQHw9QFf4zUYKVG4D9WEt3YcgfJjFTexbgScfHCMTdU',
        'E96rnFdRgtHPRGVgagHUQVoprxD8CP1hyuj7aRjppWBN',
        'AppnmrGsDvqwQXNz8yXyxJep7aEaujN1DGm3BF7jtLeA',
        'DDFVrMYLa6dZRgVXxQPFJhQX7q2Eb89p2TT4RqaoV2eq',
        '3uR7CqF23kvEKi8kvkYBVKkiwq3RwnDjL1FaXq5zo12s',
        '29ptGQcULATBK4925m8oHctN1jAdFvTDPqkyYDyPXNsh',
        '7XUVJd5E8qTCJHrYmVPDqjbXb9m8nNpsRbifekVkZe7U',
        'Y2FLDDT5Bw5mRXw2LLJti1h6sd37YDjpy3ihVRLF2ow',
        'Aeer9KvA9Z57hrUPcdhjaLGuP3wLn1NvjGWhhfSPWHnp',
        'J7WvZb3as9rsNHRzYJSfHTe8QKGM7odbgp4zLSYSWMbv',
        '8EzXfWXjwLYyyv2bBFCPwZPHsnXuy5LKDUBbTzoBdzQq',
        '4C1pAWLv9FkjdGgo4AMv6Z6yww5UNAoSfP64fPEcr12x',
        '51oF6PnJGqWP16JSCCVFc68aht2QuJdjpeanWthGiTNS',
        'FHjaYVxgU9NcCE5vRrnACS3Ng7UWyEZFvgCqAe2ZKn4H',
        '9t1Qb3qCygJt4VcsnqV8i1ffZG1oVnzRHgos48B5qtuj',
        '7L6N6byZviJqhrK92H9TQTbVESf8oBqwWUm2D2rXLFDx',
        'iT5DmwSuRucvVpt6H9pfjasatrbiCTF2QmTLim6RuHw',
        '4Nw66ZHQUopgnsE2PUFVkNtbQQj9kkE6SmPRQkVd5afs',
        '8g4X3Y27JiKWHP2YwL2eP5gFcUKqz5TsrHwsq3ADHGG8',
        'HbzhDWrFB1oe3LKqkrSQ8mSuEdGUSZZ7SBGuB4DFoZhm',
        '8HDkrsPD61TQtciGaaTSruuXHjzYmV9Z52Ua6tFyrQSb',
        'UywQpv3Wh8Js2vtTtZkmrRdaBnqZU3kvPUeoVy2s6WY',
        'GJC2NgG3T5m2tgVkjLqhUhPCuLtnPnYvAjUXZrjjtj4v',
        '9pYT3kGFsVVEooV26PcZGxwCLsGkkiWdkF5Sq4aLqyBY',
        'HArYuz7mYYD3wkqkcGeMQQ8p6CyFiaoA4w3Uc4DVecZ1',
        '9geygoaPK3yyiWz3Yyw2juWr2SXgMq1rQYQVRobGueHw',
        'Eut3ChjQAcEPkPbsvPy6iAa8Dc2ssX3nsY3EafRFwUu7',
        'F2CHoLs5gUBFJAhBV9TTATEZfDANz3t9czbMm5DodUe1',
        'G3xGNPYzWmn5XMuWXzDD1hHe7ZHDXuM8NAQh4vXqaG9K',
        'uKetBHE9KHqxypdpkyf2WFgi4rjNr94wnYnqw15tzi4',
        '9LysYNqUcNXabcSHHBA1JsiGBXbLPgXmEHenX4t3k6Ri',
        '8MNotqF9M3H9KeA17GAWatSb7uNWDZraUVukT26WhwX2',
        'FHCevK2MWx4tjmNY8ZUJSRskzrEAS2eZu5Zs9jzyJmcb',
        'BbDsCj2tEb6CCbowbfgKWn3z4jQ1jFKukjA39tTQhFj9',
        'HZecBm9HXDJkDDUcGK9YKqyY1HoTEXSVtk64zN39QBat',
        '3DVpmaGLCNpKYjVa4Ujy5m4DwbovSiEKMwnoj3tDqBEU',
        'DXzV2mDAhUTftn9LXnwVrnJrW4YXNZCFbzQHxmtv9utK',
        'Eq3krDuCtdBFPYWtnCq5CDgVPDGNvRdUq2piaeFGTM2C',
        'EwBLzoDXTza94fpqhsTVn1rbgqbDXqfjJMkVHDfdPW3z',
        'C9eb2NZx795YLRQfu3JvRcMA5BAFTPAiUXUhSG6dCQco',
        'AZYfwhkfFtgLK2JDixAth1yd4sEfVxGuRW5sKeGDrjTq',
        'C3rEkqrRjbBj7yfv98zhxv3gqxFT5LjtEPXf2khJg6SJ',
        'BkYLRifprWQUUPNGVRx24aQqqesLioKCrjBHgftBNrue',
        'HExGyUJ95VqhBfnLbsNsJHgVrBeR9CfzAWwqXEH3UKiz',
        '3ic9XxVA93uxJqrmuTodQVd9YMtpiYRTph5QCs442zSh',
        'GxyF3tdkadMP7SMPsanz3MzbuWw5s3NF6Lz3YsMo2aTm',
        'AiBXKubq7xhF2qhiDzWH3gjreFdNo7xW48VoDEe4vt4p',
        '9n3Z2KuysMT3An5GA8RG1oE4wrjtPhyMGwZh4U6ksXLf',
        '9yaxdQeQhSVddDEsmnNbgm4RmrMsWHJGs6XFE3AXYBH',
        'Cnotz3t9NtDiantBDP7X8PifnEDiAdFRsXJcLgM8eGxt',
        'BTDkKFT8M2wDBQibntY5syPqnKUbiWq8wk98snc2znwy',
        '7VxDrNaFioLB1UpPd6dZDACQZEwmX3CuMDvMHH5atK5t',
        '7GRp98NG6MakX9rAR1J77vLE1XP8kiWevUSCaYY88ue1',
        'DjSTcBoCs3MChQL7eKtz9TkE7Qfd3hrz6NCahNfeYDtU',
        '8bhvcuE8VhST1sBAcj6CFuCXf8QW8NvVcA6uUwAzSE78',
        'H84GeSwWatxeyTQubF5ZreVeRRUC51g8WB8wkqtpS3YK',
        'DpNViPzKp5grySzFmMN6Lty3yjjt2u4iNAkvWRAgsCc1',
        '9HhKEisBY76BiMR68cnr68fuqUUFo2vbzQGGLyjdXtuL',
        '6HBXqH9TW7mujmBt6pfYt66pVDFjNNf7SfRtggCjL1Ve',
        '9ovHe6qgSGnRbPLkYfGEx81tVvzfrgzrYyqKhi12d1rg',
        '8kJqXr9XtE31AQU5jBviUMPxMhfmbdbu1JjWKAaTqVdb',
        'EWZTfVVMXJsCiuCUtckg2w844mYBiEUb3DQ3nAVMJDvG',
        'Byv8djCW79MkrVMvDfxC65TY1gsoLprmzKcrLYNgJCC6',
        '5Dn5N6isEfyzu622iWRi3dkvagn7BGpB21hARCyVNtWg',
        '63yhw7EAKew2jpQG5v2mLfU4WsEjmH7AAgFZJroWboew',
        '5NfBmBCS8dGLBRvCgeHFtUnCDjdHAPRrciRvNnYniwnh',
        'GikcowdDSfKZ3wm7qPQpEqnUNMiJYKJ5UyTtgYSpz4rA',
        'CeBRHMjd6E38hXYx5JaPyUPGE6rToJNvMjdvEq9LWNB3',
        '5ApLmYCHabcU2dQFDjSuhwubWHiuDgJja8JxsCjsP5Z3',
        'HraqcZt77px2LWSw2STSimqTnxuaesg3SRk8yDXMXsei',
        '7AwrLHFnbYbgD1gZBFSJ3nbS9bhPqbxeneZExWzCQk79',
        '7Ldxw42uEoTSfDHZLQGC8xu8kPejRm2a59M3AAbn3ceG',
        'FLRWN4GThHbm8a2hUYs8sqzYhVna6iz8JvH4jpWgLKWV',
        '5rNHUBUgi1WkW6JzAjJGVGGUeWEJFbidMSB4Lr9ZviNy',
        'F4poYTcKqkAMd3W6ZJbwXA9YHQhXqgvNyC8A4Jx66SsW',
        '4ZD1v5VQE8rD4Q36CfADPgV9LfDnXBi9UZB3Vz8RX1cE',
        '3Yv2PMHRCY6rhQabrVLuEw7JLtRFEKScCyoibecVYRSR',
        '6MUbiNriugkMgR8UPKdd5CMXtTsriSaHrpFkGCzDM3dR',
        'GKpLKk3zwfvNKEjxRxi2rsX1kCV5xPtTyDskjGpnZEaA',
        '3T67PtZ6NLQCy84ZuCeAaPpmmncTWpjqANQWR6oPq8zX',
        '4pXHVcV74zcKr4nvdLiTteJFDoYi1iFV2jrSSbwHsZmA',
        'GP3RXFPsVQnB9TDZp3AWMXvTRmHGiaMccEftiXtyhAHh',
        '85oa45dXpKz3RYNjeZmcyQRgyw7mtpMtgpPrUmhZmMVm',
        '22X6bdm16tbYuNNukjxBwBihkp9gFyLCvumuAJraxAdC',
        '5nSwVbRBdat3hPwKxv9sUKT5XenV5RkEU8HeH7H4WiVo',
        '2op3HSzn6BG5is2LRpZM475kvC5B8GdUr8Wj3MMC1CtQ',
        'FVpAGjAtLnW88oHbDsrvJoxsaPtetSpM2kh5mUpxEUAc',
        'GvpHt6xgDzVKyPrkctQrmUkfmKdYHBosh6UpNRjNaxFy',
        'BsnJXLdV3CaZzhxjZKTXkT57sbkqRXdVseNsAr8dBdoP',
        'GCfFMqbuTttJ4CaS7WqL7qBNQktq8E2VecdcCL36h9Rj',
        '9cfixcKa9KPzjP3AYn5wm5BDKgheUL6RuinPMrr1EZJx',
        'j17Y5sveT2y9Ao5LWjj6u8vBMVLxoPpAnS1x4YAdYE8',
        'FhEKRiSYbT6knMfRJSgmxZeBvWQgMnYM4MV2Dh6fD1j8',
        'EJRJj5BxjdKGK8UoP4fYQdHhkKx4hXURKt4Jgrs6PWBW',
        'GWxLkJK1x17hpxrj4mHChJU76Ezot7SGAoT6QNJdSVno',
        'FgQ5rQpKE91tGppwYrB8YxJ1tMGxUc4t86P6bCGYWgWX',
        '9fg57ghCQfbMpRcLiwCwTj5p3Q3hqK6FSvojYTeuC87K',
        '7eeGthc8BuAHLWjuuimZVYJNs32fGpVH2c6srSsLKPqT',
        '26dQCkmT1iH9rktLvUMoWwM5bqf1tVutEADDFT46iSXH',
        '2eJJEyJSRSeTrc57jtnqCrSWkzQbL3EdvsDdNeXHeksK',
        'CzNs2iMRoraHVg8pEgxyju8u2XXHHhVUwEmVxU4kMtqX',
        '7sMftrr4EPPSCy4xGZxNADAEgTVVpqQPTo8jdyYFmig3',
        '96SL7poAmuJK3A7Vp9zVHxcD5obD4UfdGF411LKCDYxQ',
        '2Ymv2SnUQRKLdMutjdC2jrM5Y29tzMzoKLkEbCANMmno',
        'FRXKbvEwokSrHFKqdFpWmBy66mU3oVsgr1HdtzoPnQUX',
        'KEDh4t6nJgxZF5fxWj29fgWrEjivNPGp4QExz5GQ364',
        '24q4w6c4tssKnHrDcfZ7tgueT1WwFdfVRXYcmMEBrNRL',
        'F7GZexAaYzFTe6sLx8m3rxk245uixz2mw4P2sUxPHQB4',
        'B6aueUR2QcgR8f5g34tAf5WcW8qySn8mE26T62JgnaS5',
        'E8LteQ3ufWRxHL7RhzStBffhjAKiSQ6YXwTLgCNerQPB',
        '3QMyHUVS83TpJWCphSXfSsoZTLX9Ax16aWyg42neKZEh',
        'FHBx9A3P5vnuQDKsPcJtrpMiD5315PQ9dk2JUFnGgwWL',
        '2CotFBQdNauU12qgiLQvE7YmWuyKpCPTzZiahkBaPow1',
        'HKUtBjjP1D5eSUkeUczRgdB3DynE7wxXCaWykFWt7dj9',
        '2VnkSJmw9XYPHKk9EZAuBxqGuYjguptV6q4WbXf85qXo',
        '2UUZfJfWf4prtBFkcNaDAmmoTfc9DbRnyxEUMvD2oUuu',
        '3sNGwHWpNvaRodphSorv7ggdx3HywRJQNbBRk42mnuxY',
        'HfiMhzPziquHNLf68z6mAzYStQ4CN3SXvBAZH1ysPiJC',
        '6naxM3iDHvfTKcdazeyVpHxRVuJvqCjrNxzPCzn6WiFL',
        'BVWhjjaAHQG1dupQhK5BaUH1Qfnw7LvZJg3pYH8SkUDy',
        'GeQNpw6pkiuLVB6N2H4iJbH5FeTMbSod7WW1mNQBzzUp',
        'Bb1LK1nFDCAQhfbXxVyY1S4jmhwuaXhRaokfeVXvoV6R',
        'BgnEjzry8CThCL6vJLWp8Jb9HM6wd1kUL8YmQ8p3PCyP',
        '6BwdasmEXakNHeBVjXYjofBvrAoTV7i4B5P3oTxpjZM5',
        '48DvnhzqhbxqxpoM7LoPoPiwWpcgUonASUNSatZWFDFe',
        'AW5TLPNcnY8BVTcs4sR26JnmftSAaenkoHmZMt1GHzfX',
        'BFh6DAm3X27YUCGWiyP5QnfS5KSNY62AcfbAoCa56mC6',
        'Fmd1foXKG4CwDD7RiiMgsxkjs6jCR5cqbxLhbEbrfLbk',
        'EqYzDMVJDeEhnHTYAfiSNHYvz8cNcH6T73VLrepjmgTZ',
        'EUNvzSraFhZPMfZh34LjRDj6Y2VHDs29WHbs4h7Xs9hg',
        'UdA7Uudu282o2TkPobuR2W9MyEXo9F62o2526mJPLir',
        'ATxZ3vLxt4AxJSpYTMpRswYhHqcWijz6Ew1vWK2ebpiS',
        'Fz7GjgTwr8YRpsb6nedtgLrrB6pbCR2CyFBrcEFedjTR',
        '65j6J4AxXFjTzyYFUgYZ5b938ufYywSNV3RvdtW2fqM4',
        'AKC2s7sxk3RPQTP2rYBobpDvRKS9CPzCccNg7GnDRTRm',
        'EzHAHPu5Kqszj5xzeJZFjuFnUcC7rzRQWVGBuFpRpHGB',
        'FJZiSSPYcsX369LwUULrH67CfsVQ1fqK2h1FqFmAoTAj',
        '3U3ve7sihgpAydBYFu8WCyfpFfSKeb21ihKp1AvKSg2i',
        '66pUGUbQcgcc4tSJVPML3bt9xnCGKT994naF1VHsd6wU',
        '6gPz5Jz7ZC7LdC2N4KoZCa2EmLXDviKazJHSbX4vo1xi',
        'AKbHbhFDVZEp2uiSWYuCCDLFiUKDiRKVWKZniLiK4huC',
        '2Eexy4bvJRqPP5ETJF4Nh67Zc7UrXEP3izPtuDw9YfJg',
        'EfojmWeCesPVBgkEi6dZcLDEv3dhfNFApKA5PT1pH5CB',
        'DtuSJnsFX3FqxzCDnTq74D66bBjZhuGFtN35WjYP1vP1',
        'JEBFvNjAU1f7iYyF2vxPLXFkEXeBtEHbSctq9jFcjVKX',
        '8tAkFgskU8gtrA4ciMNLT7Qote8yMmSDATdMbDDaquWT',
        '3JPjgoiapN7tjCqZh1bY9giUTeoFdDXhjuy4eGyHnDRU',
        'A1c1ReWqkC57jvff4Ci27UYL5GmQegkHCGZz9WGLCTZg',
        'BB4yEc4Mp7QQD6kXAYmhk8mFSWBhFAoZpSn7twy1NZpN',
        'E47DFD9tzfwpjqtHvigUUg1ciFn1ZWwT2Ryruyx3Qwen',
        '5s255YdW4UU83G5bJtRYbLB6LeSMzC4erufR8qnejWVQ',
        'HgTF9ES2y61YdvHtdXGD6cS2t69EGQFUuvAkzWzUPhLq',
        '7CMdF77qC39cdp57m1mD1pbtxNCJAoJeBT33g6r5XYYU',
        'HKufYRfoDh38onW8S3LF5VX7ensW3dQossRbW9kBgdWV',
        'GkvmqQGskfXpfhcKSaghQrhDBASZXjK3BtLEMQK5tgrK',
        'B911YQeZ4nqwMbPXBhgKST4xXVeZzFXdJ6aLDvpoQtLS',
        'GeN7npX8hsjXnrcTKvVCd8ubZSCagTWtqG5KzrdNhRM9',
        'DaQVhRxzD56gxG8Gmy4Ja3Zirp8qt8TKE4CY84SN4r5W',
        'Dbtzp6XeeW2RsqAeRmRBbUvg5rFRn82LWjR2FaagZbGR'
    ]

    # Open CSV file to store results
    with open("update_gecko_terminal_data.csv", mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        # Write header
        writer.writerow(["Pair address", "bundled_buy_percent", "creator_token_launches"])

        # Loop through each pool, get data, and write to CSV
        for pool_id in pool_ids:            
            print(pool_id)
            data = get_gecko_terminal_data(pool_id, headless=True, timeout=30000)
            print(data)
            writer.writerow([
                pool_id,
                data.get("bundled_buy_percent"),
                data.get("creator_token_launches"),
            ])
            # Sleep for 2s between calls to avoid rate-limit or server overload
            time.sleep(2)

if __name__ == "__main__":    
    main()
