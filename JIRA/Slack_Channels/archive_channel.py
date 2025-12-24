import os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("SLACK_BOT_TOKEN")  

def find_channel_id_by_name(name, token):
    url = "https://slack.com/api/conversations.list"
    headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json; charset=utf-8"
    }
    params = {
        "exclude_archived": True,
        "limit": 1000,          # adjust if needed
        "types": "private_channel"
    }

    while True:
        resp = requests.get(url, headers=headers, params=params)
        data = resp.json()
        if not data.get("ok"):
            print("Error listing channels:", data.get("error"))
            return None

        for ch in data.get("channels", []):
            if ch.get("name") == name:
                return ch["id"]

        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
        params["cursor"] = cursor

    return None

def archive_channel(channel_id, token):
    url = "https://slack.com/api/conversations.archive"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {"channel": channel_id}
    resp = requests.post(url, headers=headers, json=payload)
    print("Archive response:", resp.json())

if __name__ == "__main__":
    channel_name = "teste-enzo"
    cid = find_channel_id_by_name(channel_name, TOKEN)
    if not cid:
        print("Channel not found")
    else:
        print("Channel ID:", cid)
        archive_channel(cid, TOKEN)
