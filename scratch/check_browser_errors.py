import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Listen for console logs
        page.on("console", lambda msg: print(f"[CONSOLE] {msg.type}: {msg.text}"))
        
        # Listen for page errors
        page.on("pageerror", lambda err: print(f"[PAGE ERROR] {err}"))
        
        print("Navigating to http://127.0.0.1:8502...")
        try:
            await page.goto("http://127.0.0.1:8502")
            await page.wait_for_timeout(2000)
            
            # Click the Continue with Google button
            print("Clicking Continue with Google button...")
            await page.click("#btn-google-signin")
            await page.wait_for_timeout(3000)
            
            print(f"Current URL: {page.url}")
        except Exception as e:
            print(f"Error during navigation/click: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
