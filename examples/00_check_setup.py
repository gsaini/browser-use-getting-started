"""Step 0 — check your setup. No API key, no LLM calls, no cost.

Launches the browser that browser-use will drive, opens a page, reads it back,
and closes it. If this works, every later example has a working browser
underneath it; if it fails, fix that before adding a model.

    uv run python examples/00_check_setup.py
"""

import asyncio

from browser_use import Browser
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    browser = Browser(headless=True)
    await browser.start()
    try:
        await browser.navigate_to("https://news.ycombinator.com")
        url = await browser.get_current_page_url()
        print(f"Browser OK — opened {url}")
    finally:
        await browser.kill()


if __name__ == "__main__":
    asyncio.run(main())
