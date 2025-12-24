import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
CODE = os.getenv("SLACK_OAUTH_CODE")
REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI", "https://localhost:8123/callback")

resp = requests.post(
    "https://slack.com/api/oauth.v2.access",
    data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": CODE,
        "redirect_uri": REDIRECT_URI
    }
)

print(resp.json())
