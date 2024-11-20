import asyncio, json
import os
import traceback
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from emailsender import send_email
from config import TARGET_CLASS_NUMBER,to_email,email_message,initial_cookies, payload, username, passwd, keyValue, credentialIdPadded as credentialId, rpId, userHandle, counter, keyIdentifier

if not os.path.exists('./screenshots'):
    os.makedirs('./screenshots')
cookies_path = 'cookies.json'

async def save_cookies(context):
    """Save cookies to a JSON file."""
    try:
        cookies = await context.cookies()
        with open(cookies_path, 'w') as cookies_file:
            json.dump(cookies, cookies_file)
        print(f"Cookies saved to {cookies_path}")
    except Exception as e:
        await handle_error("Error in save_cookies", e)

async def load_cookies(context):
    """Load cookies from a JSON file and set them in the browser context."""
    try:
        if os.path.exists(cookies_path):
            with open(cookies_path, 'r') as cookies_file:
                cookies = json.load(cookies_file)
                await context.add_cookies(cookies)
            print(f"Cookies loaded from {cookies_path}")
    except Exception as e:
        await handle_error("Error in load_cookies", e)
    
async def handle_error(context_message, exception, stringtrace):
    """Handle errors by logging traceback and sending an email."""
    error_trace = traceback.format_exc()
    full_message = f"{context_message}\nException: {str(exception)}\nTraceback:\n{error_trace} \n\n {stringtrace}"
    print(full_message)
    await asyncio.to_thread(send_email, f"Error in GOLD Class Monitor Script", full_message, to_email)

async def run_script():
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            await context.add_cookies(initial_cookies)
            await load_cookies(context)  # Load cookies from the last session
            
            page = await context.new_page()

            # Start the loop
            while True:
                success = await check_class_status(page, context)
                if not success:
                    print("Script concluded, or ended due to authentication issues or unexpected errors.")
                    break 
                await asyncio.sleep(10)

            await save_cookies(context)
            await errorhandler_email()
            await browser.close()
    except Exception as e:
        await handle_error("Error in run_script", e)

async def check_class_status(page, context):
    TRACE = ""
    try:
        await page.goto('https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx', wait_until='domcontentloaded')
        #screenshot
        print("Attempting to access GOLD, page navigated")
        TRACE += "Attempting to access GOLD, page navigated"
        
        await page.screenshot(path='./screenshots/step-3-gold.png')
        
        # Check if we're at the CAS login page (State S1)
        if 'sso.ucsb.edu/cas/login' in page.url:
            print("Attempting Authentication, CAS Not Authenticated: URL: ", page.url)
            TRACE += "Attempting Authentication, CAS Not Authenticated: URL: " + page.url
            await page.screenshot(path='./screenshots/step-0-auth-possible.png')
            if not await login_cas(page, context): 
                return False
            print("Attempting to access GOLD, page navigated - checking against to see if at CAS login")
            TRACE += "Attempting to access GOLD, page navigated - checking against to see if at CAS login"
            await page.screenshot(path='./screenshots/step-4-gold.png')

        
        # Go to GOLD page again
        await page.goto('https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx', wait_until='domcontentloaded')
        #screenshot
        print("Attempting to access GOLD, performing scan")
        TRACE += "Attempting to access GOLD, performing scan"

        
        # Search for the class using provided payloads
        await page.select_option('select[name="ctl00$pageContent$quarterDropDown"]', payload['ctl00$pageContent$quarterDropDown'])
        await page.select_option('select[name="ctl00$pageContent$subjectAreaDropDown"]', payload['ctl00$pageContent$subjectAreaDropDown'])
        await page.fill('input[name="ctl00$pageContent$courseNumberTextBox"]', payload['ctl00$pageContent$courseNumberTextBox'])
        await page.click('input[name="ctl00$pageContent$searchButton"]')
        await page.wait_for_load_state('networkidle')

        # Check if we were redirected to the CAS login page
        if 'sso.ucsb.edu/cas/login' in page.url:
            print("Both GOLD and CAS sessions are invalid.")
            TRACE += "Both GOLD and CAS sessions are invalid - post-click searching for class"
            return False

        # Parse and extract the desired information
        return await parse_and_process(page)
    
    except Exception as e:
        await handle_error("Error in check_class_status", e)
        return False

payload_classname = f"{payload["ctl00$pageContent$subjectAreaDropDown"]} {payload["ctl00$pageContent$courseNumberTextBox"]}"
async def parse_and_process(page):
    TRACE = ""
    try:
        # Step 1: Locate the class row
        TRACE += "Finding class selector.\n"
        class_row_selector = f'div[data-target*="{TARGET_CLASS_NUMBER}"]'
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
                    class_status = f"{payload_classname} | {class_status} | {max_seats} | Section: {TARGET_CLASS_NUMBER}"

                TRACE += f"Class status updated: {class_status}.\n"

                print(f"{datetime.now()}: {class_status}")

                # Step 4: Determine if the class is available
                if "Full" not in class_status:
                    print("Class has vancancy!")
                    TRACE += "Class is no longer full! Sending notification email.\n"

                    # Construct email message
                    email_message = f"The class is no longer full! Check GOLD to register IMMEDIATELY.\nStatus: {class_status}"
                    await asyncio.to_thread(send_email, f"URGENT: {payload_classname} HAS VACANCY", email_message, to_email)
                    return False
                else:
                    TRACE += "Class is still full.\n"
            else:
                print("Could not find class status information.")
                TRACE += "Could not find class status information.\n"
        else:
            print("Could not find the target class information.")
            TRACE += "Could not find the target class information.\n"
    except PlaywrightTimeoutError:
        await handle_error("Timeout error in parse_and_process", PlaywrightTimeoutError, TRACE)
    except Exception as e:
        await handle_error("Error in parse_and_process", e, TRACE)
    return True



#Function for: On Fatal Error, Send Email with all the information
async def errorhandler_email():
    subject = f"GOLD Class Monitor Script has ended"
    await asyncio.to_thread(send_email, subject, email_message, to_email)

async def duo_auth(page, context):
    try:
        duo_iframe_element = await page.wait_for_selector('iframe[id="duo_iframe"]', timeout=5000)
        print("Found iframe, selecting frame")
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

        # Save cookies
        await save_cookies(context)
    
    except Exception as e:
        await handle_error("Error in duo_auth", e)
    

async def login_cas(page, context):
    try:
        #screenshot 
        print("Attempting to login CAS")
        await page.screenshot(path='./screenshots/step-1-cas-login.png')
        
        await page.goto('https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx', wait_until='domcontentloaded')
        
        #screenshot
        print("Attempting to login CAS, page navigated")
        await page.screenshot(path='./screenshots/step-2-cas-login.png')
        
        print(await page.title())
        if "Login Successful" in await page.title():
            print("Already Authenticated")
            return True
        elif "Duo" in await page.title(): # We do this in case we're logged in but not 2FA Authed
            await duo_auth(page, context)
        #f no redirects then we land at title = "Login Successful - UCSB Authentication Service"
        elif "Log In" in page.title():
            print("Logging in with credentials...")
            await page.fill('input#username', username)
            await page.fill('input#password', passwd)
            await page.click('input[name="submit"]')
            await page.wait_for_load_state('commit')
            
            await duo_auth(page, context)

        return True
    except Exception as e:
        await handle_error("Error in login_cas", e)
        return False

async def save_page_content(page, name = 'page.html'):
    with open(name, 'w') as f:
        f.write(await page.content())

async def setup_virtual_authenticator(page, context):
    # Create a CDP session
    cdp = await context.new_cdp_session(page)
    await cdp.send('WebAuthn.enable')

    # Add a virtual authenticator
    result = await cdp.send('WebAuthn.addVirtualAuthenticator', {
        'options': {
            'protocol': 'ctap2',  # or 'ctap2' depending on what DUO expects
            'transport': 'internal', 
            'hasResidentKey': True, #default F , but true since we have userHandle
            'hasUserVerification': True,
            'isUserVerified': True,


        }
    })
    authenticator_id = result['authenticatorId']

    return cdp, authenticator_id

async def add_credential(cdp, authenticator_id):
    credentials = {
        'authenticatorId': authenticator_id,
        'credential': {
            'credentialId': credentialId,
            'isResidentCredential': True, #f
            'rpId': rpId,
            'privateKey': keyValue,
            'userHandle': userHandle,
            'signCount': counter,
        }
    }
    await cdp.send('WebAuthn.addCredential', credentials)
    
    # Verify: 
    # await get_credentials(cdp, authenticator_id)
    
#Debug
async def handle_webauthn_request(params):
    print(f"WebAuthn.getAssertion Event: {json.dumps(params, indent=2)}")
            
async def get_credentials(cdp, authenticator_id):
    print("Retrieving credentials...")
    try:
        credentials = await cdp.send('WebAuthn.getCredentials', {
            'authenticatorId': authenticator_id
        })
        print(credentials)

    except Exception as e:
        print(f"Error retrieving credentials: {e}")

asyncio.run(run_script())
