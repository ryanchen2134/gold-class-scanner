from dotenv import load_dotenv
import os
load_dotenv(override=True)

start_time = None

HEADLESS = True

TARGET_CLASS_NUMBER = '42747' # 120B stats

cookies_path = 'cookies.json'
#default email message
email_message = "An error occurred while running the program. Please check the logs for more information.\n"

payload = {
    
    "ctl00$pageContent$quarterDropDown": "20251", #2025 winter
    "ctl00$pageContent$subjectAreaDropDown": "PSTAT",
    "ctl00$pageContent$courseNumberTextBox": "120B",
    
    "ctl00$pageContent$HiddenTextBox": "",
    "ctl00$pageContent$searchButton": "Search",
    "__EVENTTARGET": "",
    "__EVENTARGUMENT": "",
    "__LASTFOCUS": ""
}


auth_log = []
cas_auth_counter = int(0)
duo_auth_counter = int(0)

payload_classname = payload["ctl00$pageContent$subjectAreaDropDown"] + \
    " " + payload["ctl00$pageContent$courseNumberTextBox"]


# Sensitive Personal Information

HOPT_COUNTER = int(os.environ['HOPT_COUNTER'])

HOPT_KEY = os.environ['HOPT_KEY']



to_email = "rueianchen@gmail.com"

## Private Key
#this one is used propietary by DUO
keyIdentifier = os.environ['keyIdentifier']

# base64, padded 
keyValue = os.environ['keyValue']
#base64, padded
credentialIdPadded = os.environ['credentialIdPadded']

rpId= "duosecurity.com"


# Base64 encoded
userHandle= os.environ['userHandle']
counter= int(os.environ['counter'])

## Email
email_addr = os.environ['email_addr']
email_password = os.environ['email_password']

## UCSB Login
username = os.environ['username']
passwd = os.environ['passwd']




initial_cookies = [
    # Auto Auth implemented
]
