import asyncio, json
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from emailsender import send_email
from config import initial_cookies, payload, username, passwd, keyValue, credentialIdPadded as credentialId, rpId, userHandle, counter, keyIdentifier



TARGET_CLASS_NUMBER = '41129' 
to_email = "rueianchen@gmail.com"
email_message = "An error occurred while running the program. Please check the logs for more information.\n"
async def run_script():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        
        # Set initial cookies
        await context.add_cookies(initial_cookies)

        page = await context.new_page()

        # Start the loop
        while True:
            success = await check_class_status(page, context)
            if not success:
                print("Script concluded, or ended due to authentication issues or unexpected errors.")
                break 


            await asyncio.sleep(10)

            

        await errorhandler_email()
        await browser.close()

async def check_class_status(page, context):
    
    try:

        await page.goto('https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx', wait_until='domcontentloaded')


        await save_page_content(page)
        
        # Check if we're at the CAS login page (State S1)
#        # a: Login Page, b: Duo Page
        if 'sso.ucsb.edu/cas/login' in page.url:
            print("Attempting Authentication, CAS Not Authenticated: URL: ", page.url)

            if not await login_cas(page, context): return False

        # We could have been at S2 so
        await page.goto('https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx', wait_until='domcontentloaded')

        await save_page_content(page)

        # elements easily found in dom inspector
        await page.select_option('select[name="ctl00$pageContent$quarterDropDown"]', payload['ctl00$pageContent$quarterDropDown'])

        await page.select_option('select[name="ctl00$pageContent$subjectAreaDropDown"]', payload['ctl00$pageContent$subjectAreaDropDown'])

        await page.fill('input[name="ctl00$pageContent$courseNumberTextBox"]', payload['ctl00$pageContent$courseNumberTextBox'])

        await page.click('input[name="ctl00$pageContent$searchButton"]')

        await page.wait_for_load_state('networkidle')

        # Check if we've been redirected to the CAS login page (State S1)
        if 'sso.ucsb.edu/cas/login' in page.url:
            print("Both GOLD and CAS sessions are invalid.")
            return False

        # At this point, we should be on the results page
        # Proceed to parse and extract the desired information
        return await parse_and_process(page)

    except Exception as e:
        print(f"An error occurred: {e}")
        return False

async def parse_and_process(page):
    try:
        class_row_selector = f'div[data-target*="{TARGET_CLASS_NUMBER}"]'
        await page.wait_for_selector(class_row_selector, timeout=10000)

        class_row = await page.query_selector(class_row_selector)

        if class_row:
            # unique selector for this class
            status_selector = '.col-lg-search-space.col-md-space.col-sm-push-1.col-sm-space.col-xs-2'
            space_element = await class_row.query_selector(status_selector)
            if space_element:
                class_status = await space_element.inner_text()
                class_status = class_status.strip()
                print(f"{datetime.now()}: Class {TARGET_CLASS_NUMBER} status: {class_status}")
                
                
                if "Full" not in class_status:
                    print("Class is no longer full!")

                    email_message = "The class {TARGET_CLASS_NUMBER} is no longer full! Check GOLD to register. f{class_status}"
                    #stop the program
                    return False
                
                
            else:
                print("Could not find class status information.")
        else:
            print("Could not find the target class information.")
    except PlaywrightTimeoutError:
        print("Timeout occurred while waiting for the search results.")
    except Exception as e:
        print(f"An error occurred while parsing the page: {e}")
    return True

#Function for: On Fatal Error, Send Email with all the information
async def errorhandler_email():
    subject = f"GOLD Class Monitor Script has ended"
    await asyncio.to_thread(send_email, subject, email_message, to_email)


async def login_cas(page, context):
    
    await page.goto('https://sso.ucsb.edu/cas/login', wait_until='domcontentloaded')
    await page.fill('input#username', username)
    await page.fill('input#password', passwd)
    await page.click('input[name="submit"]')
    await page.wait_for_load_state('commit')
    # if "Login Successful" is the titel of the page, then we are logged in
    if("Login Successful" in await page.title() ):
        #issue with logic, DUO security might not be authenticated still.
        await page.goto('https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx', wait_until='domcontentloaded') 
        if ("Duo" in await page.title() ):
            print("DUO Authentication Required. Attempting- Searching for iframe")
            duo_iframe_element = await page.wait_for_selector('iframe[id="duo_iframe"]', timeout=5000)
            print("Found iframe, selecting frame")
            duo_frame = await duo_iframe_element.content_frame()
            await duo_frame.wait_for_load_state('domcontentloaded')
            print("DUO Frame Loaded, searching for button")
            # wait for the fieldset containing the unique key identifier to be visible
            # is the unique bitwarden generated passkey
            await duo_frame.wait_for_selector(f'fieldset[data-device-index="{keyIdentifier}"]', timeout=2000)
            # find auth button
            await duo_frame.wait_for_selector(f'fieldset[data-device-index="{keyIdentifier}"] button.auth-button', timeout=2000)
            # Hitting checkbox for 10h remember
            await duo_frame.check('input[name="dampen_choice"]')

            print("Clicking the 'Use Security Key' button.")
            await duo_frame.click(f'fieldset[data-device-index="{keyIdentifier}"] button.auth-button')

            
            # Duo Opens a new window, wait for the new window to open
            auth_page = await page.wait_for_event('popup')
                #Might expect_event
                #Race conditions prevented because await stalls, thus we can get 
                #the Webauthn Cred and Auth attached before DUO JS calls navigator.credentials.get
            cdp, authenticator_id = await setup_virtual_authenticator(auth_page, context)
            # Add the credential to the authenticator
            cdp.on('WebAuthn.getAssertion', handle_webauthn_request)
            # event to detect credential added. If this line doesnt run, events are down
            cdp.on('WebAuthn.credentialAdded', lambda params: print(f"Credential added: {params}"))
            await add_credential(cdp, authenticator_id)

            #Sleep for 10 seconds to allow the DUO JS to call navigator.credentials.get,
            #and for the virtual authenticator to respond with the credential
            await asyncio.sleep(10)
            # reload to see if we are authenticated
            await page.goto('https://my.sa.ucsb.edu/gold/BasicFindCourses.aspx', wait_until='domcontentloaded') 
            
            await asyncio.sleep(3)
            
            if ("Duo" not in await page.title()):
                print("DUO Authentication Successful")
                return True
            else:
                print("DUO Authentication Failed")
        else: 
            print("DUO Authentication Not Required, Login Successful")
            return True
    print("CAS Authentication Failed")
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
