import asyncio
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright


# def test_gatekept_load():
#     test_string = "43xqhxrE88jgKRvXJm1XmZ7bgyXCKHhq1R3NR8V1pump"

#     with sync_playwright() as p:
#         # 1) Launch a headed browser for debugging
#         browser = p.chromium.launch(headless=False)
#         page = browser.new_page()

#         # 2) Go to https://gatekept.io/
#         page.goto("https://gatekept.io/")

#         # 3) Fill the input box
#         page.get_by_placeholder("Enter A Solana Token").fill(test_string)

#         # 4) Click the 'Search' button (this works as you said)
#         page.click("text=Search")

#         # 5) Wait for the loading to finish.
#         #    We can do this by waiting for the element's text to no longer be "Loading...".
#         #    We'll use page.wait_for_function so we can check the text content dynamically.
#         page.wait_for_function("""
#             () => {
#                 const el = document.querySelector("p.cabal-chance-value");
#                 return el && el.textContent.trim() !== "Loading...";
#             }
#         """)

#         # 6) Now the text is no longer "Loading...", so fetch the result.
#         result_value = page.inner_text("p.cabal-chance-value")
#         print("Chance value:", result_value)

#         # Pause to see the result in the headed browser
#         input("Press Enter to close the browser...")
#         browser.close()

# if __name__ == "__main__":
#     test_gatekept_load()



async def test_gatekept_input():
    test_string = "43xqhxrE88jgKRvXJm1XmZ7bgyXCKHhq1R3NR8V1pump"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://gatekept.io/")

        # Fill the input
        await page.get_by_placeholder("Enter A Solana Token").fill(test_string)

        # Click 'Search'
        await page.locator(".search-button").click()

        # Wait for the chance value to finish loading
        await page.wait_for_function(
            """
            () => {
                const el = document.querySelector("p.cabal-chance-value");
                return el && el.textContent.trim() !== "Loading...";
            }
            """,
            timeout=60_000
        )

        result_value = await page.inner_text("p.cabal-chance-value")
        print("Chance value:", result_value)


        # Wait for the container to appear (ignoring the color class entirely)
        await page.wait_for_selector("div.meta-value-container", timeout=60_000)
        second_value = await page.inner_text("div.meta-value-container")
        print("Second value:", second_value)


        # Wait for the meta-value-container to be visible (regardless of color class)
        # await page.wait_for_selector("div.meta-value-container", timeout=60_000)
        # second_value = await page.inner_text("div.meta-value-container")
        # print("Second value:", second_value)

        input("Press Enter to close the browser...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_gatekept_input())
