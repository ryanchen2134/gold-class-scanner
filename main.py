import utils
import threading
from playwright.async_api import async_playwright
from random import randint

utils.load_dotenv(override=True)

async def run_script():
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=utils.config.HEADLESS)
        context = await browser.new_context()

        await context.add_cookies(utils.config.initial_cookies)

        # Load cookies from the last session
        if not await utils.load_cookies(context):
            raise Exception(
                "Could not load cookies from previous run. Abort Abort Abort!!!")
        
        page = await context.new_page()

        # main logic loop
        while True:

            if not await utils.check_class_status(page, context):
                # this function will return true if it didn't have an issue and that the class is still full
                print("Script concluding")
                break
            await utils.asyncio.sleep(randint(3, 6) + randint(randint(-2, 1), randint(1, 3)))

        if not await utils.save_cookies(context):
            raise Exception("Could not save cookies.")
        await browser.close()

if __name__ == "__main__":
    
    health_thread = threading.Thread(target=utils.start_health_server, daemon=True)
    health_thread.start()
    
    utils.asyncio.run(run_script())