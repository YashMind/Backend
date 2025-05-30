# paypal_service.py
import os
from paypalcheckoutsdk.core import PayPalHttpClient, SandboxEnvironment, LiveEnvironment
from decouple import config

class PayPalClient:
    def __init__(self):
        self.client_id = config("PAYPAL_CLIENT_ID")
        self.client_secret = config("PAYPAL_SECRET")
        self.mode = config("PAYPAL_MODE", default="sandbox")
        
        if self.mode == "live":
            self.environment = LiveEnvironment(
                client_id=self.client_id, 
                client_secret=self.client_secret
            )
        else:
            self.environment = SandboxEnvironment(
                client_id=self.client_id, 
                client_secret=self.client_secret
            )
            
        self.client = PayPalHttpClient(self.environment)