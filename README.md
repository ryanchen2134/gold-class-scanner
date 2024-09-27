This is a tool to scan a specific class, info in payload under config.py
    Intercept a POST request's form-data for this information
    Hardcoded for classes, easily adaptable for sections.

Useful for classes that don't have waitlists.

Auto-auth, given secret key (Fido, u2f) already authenticated.
    Attestation not implemented, assertion (2fa auth) implemented.
    Will auto-auth if session expires. # gold-class-scanner
