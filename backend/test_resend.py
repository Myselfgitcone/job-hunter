"""
Quick test — run this to verify Resend email works.
Usage: python test_resend.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("RESEND_API_KEY", "re_Sok9Bh5J_5mchCmU5mPDJmmWLbFaE6LqE")
TO_EMAIL = "jaggubhai8766@gmail.com"

print(f"Using API key: {API_KEY[:12]}...")
print(f"Sending to: {TO_EMAIL}")

try:
    import resend
    resend.api_key = API_KEY
    result = resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": [TO_EMAIL],
        "subject": "Job Hunter — Test Email",
        "html": "<h2>✅ Resend is working!</h2><p>If you see this, email sending is configured correctly.</p>",
    })
    print(f"✅ SUCCESS! Email sent. ID: {result}")
except ImportError:
    print("❌ resend package not installed. Run: pip install resend")
except Exception as e:
    print(f"❌ FAILED: {e}")
