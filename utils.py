import config
import asyncio
import json
import os
import traceback
import uvicorn
from health_server import app
from datetime import datetime
from emailsender import send_email
from dotenv import load_dotenv
import pyotp

config.start_time = datetime.now()
    
if not os.path.exists('./screenshots'):
    os.makedirs('./screenshots')
    
async def handle_error(context_message, exception, stringtrace="---no string trace---"):
    """Handle errors by logging traceback and sending an email."""
    error_trace = traceback.format_exc()
    full_message = f"{context_message}\nException: {str(exception)}\nTraceback: \n{error_trace}\n Authentication log:\n{config.auth_log} Stringtrace: \n\n {stringtrace}"
    print(full_message, stringtrace)
    await asyncio.to_thread(send_email, f"Error in GOLD Class Monitor Script", full_message, config.to_email)

async def load_cookies(context) -> bool:
    """Load cookies from a JSON file and set them in the browser context."""
    try:
        if os.path.exists(config.cookies_path):
            with open(config.cookies_path, 'r') as cookies_file:
                cookies = json.load(cookies_file)
                await context.add_cookies(cookies)
            # print(f"Cookies loaded from {cookies_path}")
    except Exception as e:
        await handle_error("Error in load_cookies", e, "")
        return False

    return True

def update_env_variable(key, value):
    """Update the specified environment variable in the .env file."""
    env_file_path = '.env'
    with open(env_file_path, 'r') as file:
        lines = file.readlines()

    with open(env_file_path, 'w') as file:
        for line in lines:
            if line.startswith(f"{key}="):
                # Update the value of the key
                file.write(f"{key}={value}\n")
            else:
                file.write(line)

    # Update the dotenv module
    load_dotenv(override=True)


async def save_cookies(context) -> bool:
    """Save cookies to a JSON file."""
    try:
        cookies = await context.cookies()
        with open(config.cookies_path, 'w') as cookies_file:
            json.dump(cookies, cookies_file)
        # print(f"Cookies saved to {cookies_path}")
    except Exception as e:
        await handle_error("Error in save_cookies", e, "")
        return False

    return True


async def check_class_status(page, context) -> bool:
    TRACE = ""
    try:
        await page.goto('https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx', wait_until='domcontentloaded')
        # screenshot
        # print("Attempting to access GOLD, page navigated")
        TRACE += "Attempting to access GOLD, page navigated"

        await page.screenshot(path='./screenshots/step-3-gold.png')

        # Check if we're at the CAS login page (State S1)
        if 'sso.ucsb.edu/cas/login' in page.url:
            # print("Attempting Authentication, CAS Not Authenticated: URL: ", page.url)
            TRACE += "Attempting Authentication, CAS Not Authenticated: URL: " + page.url
            await page.screenshot(path='./screenshots/step-0-auth-possible.png')
            if not await login_cas(page, context):
                return False  # was not able to login at all
            #save cookies
            if not await save_cookies(context):
                raise Exception("Cookies did not fit in jar.")
            # print("Attempting to access GOLD, page navigated - checking against to see if at CAS login")
            TRACE += "Attempting to access GOLD, page navigated - checking against to see if at CAS login"
            await page.screenshot(path='./screenshots/step-4-gold.png')

        # Go to GOLD page again
        await page.goto('https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx', wait_until='domcontentloaded')
        # screenshot

        # Check if we were redirected to the CAS login page
        # if that's the case then we're hopeless since the auth function failed
        # but still returned true somehow
        if 'sso.ucsb.edu/cas/login' in page.url:
            # print("Both GOLD and CAS sessions are invalid.")
            print("Reauthentication Failure: Both GOLD and CAS sessions are invalid")
            raise Exception("Both GOLD and CAS sessions are invalid, and reauthentication failed.")
        
        TRACE += "Valid Session, continuing main logic."

        await page.screenshot(path='./screenshots/step-5-gold.png')
        # print("Attempting to access GOLD, performing scan")
        TRACE += "Attempting to access GOLD, performing scan"

        # Search for the class using provided payloads
        await page.select_option('select[name="ctl00$pageContent$quarterDropDown"]', config.payload['ctl00$pageContent$quarterDropDown'])
        await page.select_option('select[name="ctl00$pageContent$subjectAreaDropDown"]', config.payload['ctl00$pageContent$subjectAreaDropDown'])
        await page.fill('input[name="ctl00$pageContent$courseNumberTextBox"]', config.payload['ctl00$pageContent$courseNumberTextBox'])
        await page.click('input[name="ctl00$pageContent$searchButton"]')
        await page.wait_for_load_state('networkidle')

        # Parse and extract the desired information
        return await parse_and_process(page)

    except Exception as e:
        await handle_error("Error in check_class_status", e, TRACE)
        return False

async def parse_and_process(page):
    TRACE = ""
    try:
        # Step 1: Locate the class row
        TRACE += "Finding class selector.\n"
        class_row_selector = f'div[data-target*="{config.TARGET_CLASS_NUMBER}"]'
        await page.wait_for_selector(class_row_selector, timeout=10000)
        class_row = await page.query_selector(class_row_selector)

        if class_row:
            # Step 2: Extract class status
            TRACE += "Class row found.\nExtracting class status.\n"
            status_selector = '.col-lg-search-space.col-md-space.col-sm-push-1.col-sm-space.col-xs-2'
            space_element = await class_row.query_selector(status_selector)

            if space_element:
                class_status = await space_element.inner_text()
                class_status = class_status.strip()

                # Step 3: Extract maximum seats available and append it to class_status
                TRACE += "Extracting maximum seats.\n"
                max_selector = '.col-lg-days.col-md-space.col-sm-push-1.col-sm-space.col-xs-2'
                max_element = await class_row.query_selector(max_selector)
                max_seats = None

                if max_element:
                    max_seats = await max_element.inner_text()
                    max_seats = max_seats.strip()
                    class_status = f"{config.payload_classname} | {class_status} | {max_seats} | Section: {config.TARGET_CLASS_NUMBER}"

                TRACE += f"Class status updated: {class_status}.\n"

                print(f"{datetime.now()}: {class_status}")

                # Step 4: Determine if the class is available
                if "Full" not in class_status:
                    print("Class has vancancy!")
                    TRACE += "Class is no longer full! Sending notification email.\n"
                    email_message = f"The class is no longer full! Check GOLD to register IMMEDIATELY.\nStatus: {class_status}"
                    await asyncio.to_thread(send_email, f"URGENT: {config.payload_classname} HAS VACANCY", email_message, config.to_email)
                    return False  # returns twice, and breaks the main loop
                else:
                    TRACE += "Class is still full.\n"
            else:
                # print("Could not find class status information.")
                raise Exception("Could not find class status information.")
        else:
            # print("Could not find the target class information.")
            raise Exception("Could not find the target class information.")

    except Exception as e:
        await handle_error("Error in parse_and_process", e, TRACE)
        return False

    return True


# Function for: On Fatal Error, Send Email with all the information
async def errorhandler_email():
    subject = f"GOLD Class Monitor Script has ended"
    await asyncio.to_thread(send_email, subject, config.email_message, config.to_email)


async def duo_auth_hopt(page, context) -> bool:
    config.duo_auth_counter += 1
    #append current date and time to AUTH_LOG
    config.auth_log.append(f"DUO Auth Counter: {config.duo_auth_counter} at {datetime.now()}")
    TRACE = ""
    print("Attempting to authenticate with DUO with extracted HOPT key and counter")
    TRACE += "Attempting to authenticate with DUO with extracted HOPT key and counter\n"
    try:

        await page.screenshot(path='./screenshots/duo-hopt-auth-0.png')

        TRACE += "Locating iframe\n"
        duo_iframe_element = await page.wait_for_selector('iframe[id="duo_iframe"]', timeout=5000)
        # print("Found iframe, selecting frame")
        TRACE += "Found iframe, selecting iframe\n"
        duo_frame = await duo_iframe_element.content_frame()
        await duo_frame.wait_for_load_state('domcontentloaded')

        await duo_frame.page.screenshot(path='./screenshots/duo-hopt-auth-1.png')
        # Device selection
        TRACE += "Selecting device\n"
        device_select_locator = '#login-form > fieldset > div > select[name="device"]'
        await duo_frame.wait_for_selector(device_select_locator, state='visible', timeout=5000)
        await duo_frame.select_option(selector=device_select_locator, value="phone2")

        await duo_frame.page.screenshot(path='./screenshots/duo-hopt-auth-2.png')
        # Check "remember for 10 hours"
        TRACE += "Checking remember for 10 hours\n"
        remember_checkbox_locator = '#login-form input[name="dampen_choice"]'
        await duo_frame.wait_for_selector(remember_checkbox_locator, state='visible', timeout=5000)
        await duo_frame.check(selector=remember_checkbox_locator)

        await duo_frame.page.screenshot(path='./screenshots/duo-hopt-auth-3.png')
        TRACE += "Locating target fieldset\n"
        fieldset_locator = 'fieldset[data-device-index="phone2"]'
        await duo_frame.wait_for_selector(fieldset_locator, state='visible', timeout=5000)
        fieldset = await duo_frame.query_selector(fieldset_locator)

        await duo_frame.page.screenshot(path='./screenshots/duo-hopt-auth-4.png')
        TRACE += "Locating passcode field button toggle\n"
        enter_passcode_button_locator = 'button#passcode.positive.auth-button'
        enter_passcode_button = await fieldset.query_selector(enter_passcode_button_locator)
        if enter_passcode_button:
            await enter_passcode_button.click()
        else:
            #raise exception
            raise Exception("Could not find the enter passcode button.")

        await duo_frame.page.screenshot(path='./screenshots/duo-hopt-auth-5.png')
        TRACE += "Locating passcode input field\n"
        passcode_input_locator = 'div.passcode-input-wrapper input[name="passcode"]'
        passcode_input = await fieldset.query_selector(passcode_input_locator)
        if not passcode_input:
            raise Exception("Passcode input field not found.")

        await duo_frame.page.screenshot(path='./screenshots/duo-hopt-auth-6.png')
        # Generate HOTP code
        TRACE += "Generating HOTP code\n"
        hotp = pyotp.HOTP(config.HOPT_KEY)

        # Referencing nonexistent variable here apparently for some reason so
        # this is a quick fix

        hotp_code = hotp.at(config.HOPT_COUNTER)
        TRACE += f"Generated HOTP code: {hotp_code}, at counter= {config.HOPT_COUNTER}\n"
        print(f"Generated HOTP code: {hotp_code}, filling form")
        TRACE += "Filling passcode input field\n"
        await passcode_input.fill(hotp_code)

        # if program fails here, HOPT_COUNTER is not incremented which is good
        # no update is sent to the server and their counter is still in sync

        TRACE += "Incrementing HOPT counter and saving to environment\n"
        config.HOPT_COUNTER = config.HOPT_COUNTER+1
        update_env_variable("HOPT_COUNTER", config.HOPT_COUNTER)

        await duo_frame.page.screenshot(path='./screenshots/duo-hopt-auth-7.png')
        TRACE += "Locating login button\n"
        login_button_locator = 'button#passcode.positive.auth-button'
        login_button = await fieldset.query_selector(login_button_locator)
        if login_button:
            try:
                await login_button.click()
                TRACE += "Clicked login button\n"
            except Exception as e:
                update_env_variable("HOPT_COUNTER", config.HOPT_COUNTER-1)
                raise Exception("Could not click the login button.", e)

        await duo_frame.page.screenshot(path='./screenshots/duo-hopt-auth-8.png')
        # wait for page to settle
        await duo_frame.wait_for_load_state('domcontentloaded')
        # screenshot
        # print("Attempting to login CAS, page navigated")
        await page.screenshot(path='./screenshots/step-5-duo-auth.png')

        # don't proceed until duo_frame closes
        await page.wait_for_load_state('domcontentloaded')

        await page.screenshot(path='./screenshots/duo-hopt-auth-9.png')

        # need to implement checking the website to see if its still CAS
        
        #duo_frame.page could cause a data race condition
        
        try:
            await page.wait_for_selector('iframe#duo_iframe', state='detached', timeout=10000)
            print("Duo iframe has closed. Likely authenticated.")
            TRACE += "DUO authentication successful\n"
        except Exception as e:
            raise Exception("HOPT Authentication failed: Duo iframe did not disappear 10 seconds after auth. Likely failed.",e)


        TRACE += "DUO authentication successful\n"
        print("DUO CAS HOPT authentication successful")
        # Save cookies
        if not await save_cookies(context):
            raise Exception(
                "Cookies did not fit in jar. Abandoning ship!!! Klingons Attacking Lower Decks!!! Also, Cowbows in Black Hats.")
    except Exception as e:
        await handle_error("Error in duo_auth", e, TRACE)
        return False

    #save cookies
    return True


async def duo_auth_push(page, context) -> bool:
    try:
        duo_iframe_element = await page.wait_for_selector('iframe[id="duo_iframe"]', timeout=5000)
        # print("Found iframe, selecting frame")
        duo_frame = await duo_iframe_element.content_frame()
        await duo_frame.wait_for_load_state('domcontentloaded')

        # Device selection
        device_select_locator = '#login-form > fieldset > div > select[name="device"]'
        await duo_frame.wait_for_selector(device_select_locator, state='visible', timeout=5000)
        await duo_frame.select_option(selector=device_select_locator, value="phone1")

        # Check "remember for 10 hours"
        remember_checkbox_locator = '#login-form input[name="dampen_choice"]'
        await duo_frame.wait_for_selector(remember_checkbox_locator, state='visible', timeout=5000)
        await duo_frame.check(selector=remember_checkbox_locator)

        # Click "Send Me a Push"
        send_push_button_locator = '#login-form button.auth-button[type="submit"]'
        await duo_frame.wait_for_selector(send_push_button_locator, state='visible', timeout=5000)
        await duo_frame.click(selector=send_push_button_locator)

        # wait for page to settle
        await duo_frame.wait_for_load_state('domcontentloaded')
        # screenshot
        # print("Attempting to login CAS, page navigated")
        await duo_frame.page.screenshot(path='./screenshots/step-5-duo-auth.png')

        # don't proceed until duo_frame closes
        await duo_frame.wait_for_load_state('networkidle')

        # Save cookies, this can be a critical point.
        # we don't want to keep reauthenticating DUO.
        # its suspicious and can lead to account lockout
        if not await save_cookies(context):
            raise Exception("Cookies did not fit in jar.")

    except Exception as e:
        await handle_error("Error in duo_auth", e, "")
        return False

    return True


async def login_cas(page, context) -> bool:
    config.cas_auth_counter += 1
    config.auth_log.append(f"CAS Auth Counter: {config.cas_auth_counter} at {datetime.now()}")
    try:
        # screenshot
        print("Reauthentication Required, attempting to login CAS")
        await page.screenshot(path='./screenshots/step-1-cas-login.png')

        await page.goto('https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx', wait_until='domcontentloaded')

        # screenshot
        # print("Attempting to login CAS, page navigated")
        await page.screenshot(path='./screenshots/step-2-cas-login.png')

        # print(await page.title())
        if "Login Successful" in await page.title():
            # Session is still valid
            return True
        elif "Duo" in await page.title():  
        # We do this in case we're CAS authed but not DUO authed
            return await duo_auth_hopt(page, context)
        # f no redirects then we land at title = "Login Successful - UCSB Authentication Service"
        elif "Log In" in await page.title():
            #We are not CAS authed
            
            # print("Logging in with credentials...")
            #wait for elements to load
            await page.wait_for_selector('input#username', state='attached')
            await page.fill('input#username', config.username)

            await page.wait_for_selector('input#password', state='attached')
            await page.fill('input#password', config.passwd)

            # screenshot
            await page.screenshot(path='./screenshots/step-2a-cas-login-form-filled.png')
            
            submit_button_selector = 'input[name="submit"].btn.btn-block.btn-submit'
            #waiting for button to become visible
            try:
                await page.wait_for_selector(submit_button_selector, state='visible', timeout=5000)
            except Exception as e:
                raise Exception("Submit button not --visible--, despite filling in fields. Logs:\n", e)
            
            button_element = await page.query_selector(submit_button_selector)
            try:
                if await button_element.is_enabled():
                    await button_element.click()
            except Exception as e:
                raise Exception("Submit button not --enabled--, despite filling in fields. Logs:\n", e)
                
            await page.wait_for_load_state('commit')

            await page.screenshot(path='./screenshots/step-3-cas-login.png')

            # wait for page to settle
            #wait 2 seconds
            await asyncio.sleep(2)
            #wait for networkidle
            await page.wait_for_load_state('networkidle')
            await page.wait_for_load_state('domcontentloaded')
            # screenshot
            # print("Attempting to login CAS, page navigated")
            await page.screenshot(path='./screenshots/step-4-cas-login.png')

            #if we've reached this point, we have the two possibilities:
            # 1. We are DUO authenticated
            # 2. We are not DUO authenticated
            # observing redirect logic, if we were DUO authed, we would be redirected to GOLD so just page url starts with gold url, else if "Duo" in await page.title(): then auth.
            if "Duo" in await page.title():
                return await duo_auth_hopt(page, context)
            elif "Login Successful" in await page.title() or page.url.startswith("https://my.sa.ucsb.edu/gold/"):
                return True
            #https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx
            
        raise Exception(f"CAS Login Failed, unexpected state: {await page.title()}")

    except Exception as e:
        await handle_error("Error in login_cas", e, "")
        return False


async def save_page_content(page, name='page.html'):
    with open(name, 'w') as f:
        f.write(await page.content())


def start_health_server():
    # Run the FastAPI server using Uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="info")
