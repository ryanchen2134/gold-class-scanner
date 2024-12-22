# gold-class-scanner

This is a tool to scan a specific class, info in payload under config.py
    Intercept a POST request's form-data for this information
    Coded for section ID, easily adaptable for sections.

Refreshes (get) to ensure valid session and code is looped on a random time interval so we don't get blocked for suspicious activity or such.
also 

Emails you if script crashes with error message, or if class is found so you can go manually register for class.

Useful for classes that don't have waitlists enabled.

Requires extraction of HOPT key from DUO, did this by extracting from DUO App on emulated android device with root access.
make sure that DUO device is only used from this script as HOPT requires counter, unlike TOPT, so major deviation from their Backend counter will result in invalid codes.

### Future implementation
* Over time the server will not accept requests and session is invalidated (without explicitly sending you back to reauth process) probably due to too many requests caused some sort of unexpected behavior on server code
need to implement better random time intervals
quick fix: need to dump cookies and reauth CAS, DUO, and GOLD if session no longer valid or unexpected error on server side

* Add section if it becomes free so user doesnt need to go add it manually.
quite easily implementable

