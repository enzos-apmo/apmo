import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ========= CONFIG =========

name_format = "bkr_development_"

TEAMS = [
    'Adquirência', 'Autorizadores', 'Benefícios', 'Caixinha', 'Cartão', 'Conta',
    'Crédito', 'Investimento', 'Misc', 'Novos-Cores', 'Onboarding',
    'Regulatório', 'Transacional'
]

SLACK_CHANNELS_GESTAO = [name_format + team.lower() + "-gestão" for team in TEAMS]
SLACK_CHANNELS_OPERACAO = [name_format + team.lower() + "-operação" for team in TEAMS]

# IDs das pessoas que vão entrar em TODOS os canais
COMMON_USERS = [
    "U04VDUQJM4P",  # Victor Freitas
    # "U07NZ0M0S9K",  # Leonardo Nori
]

# ID da pessoa extra só para canais de gestão
GESTAO_EXTRA_USER = "U06JRM6AJ" # Marabita

# ========= API HELPERS =========

def create_slack_channel(channel_name: str, token: str) -> dict:
    url = "https://slack.com/api/conversations.create"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "name": channel_name,
        "is_private": True
    }

    response = requests.post(url, headers=headers, json=payload)
    result = response.json()

    if result.get("ok"):
        real_name = result["channel"]["name"]
        print(f"✓ Channel '{channel_name}' created as '{real_name}'")
    else:
        error = result.get("error", "Unknown error")
        print(f"✗ Failed to create channel '{channel_name}': {error}")

    return result


def invite_users_to_channel(channel_id: str, user_ids: list[str], token: str) -> None:
    """
    Invite multiple users to a channel.
    Slack expects a comma-separated list of user IDs.
    """
    if not user_ids:
        return

    url = "https://slack.com/api/conversations.invite"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "channel": channel_id,
        "users": ",".join(user_ids)
    }
    resp = requests.post(url, headers=headers, json=payload)
    data = resp.json()

    if not data.get("ok"):
        # erros comuns: already_in_channel, cant_invite_self, etc.
        print(f"  ⚠ Invite error for {channel_id}: {data.get('error')}")


# ========= BULK CREATION =========

def create_all_channels():
    token = os.getenv("SLACK_USER_TOKEN")
    if not token:
        print("Error: SLACK_USER_TOKEN not found in .env file")
        return

    print(f"Creating {len(SLACK_CHANNELS_GESTAO) + len(SLACK_CHANNELS_OPERACAO)} Slack channels...\n")

    # Canais de GESTÃO: você + COMMON_USERS + GESTAO_EXTRA_USER
    for channel in SLACK_CHANNELS_GESTAO:
        res = create_slack_channel(channel, token)
        if res.get("ok"):
            cid = res["channel"]["id"]
            invite_users_to_channel(cid, COMMON_USERS + [GESTAO_EXTRA_USER], token)

    # Canais de OPERAÇÃO: você + COMMON_USERS
    for channel in SLACK_CHANNELS_OPERACAO:
        res = create_slack_channel(channel, token)
        if res.get("ok"):
            cid = res["channel"]["id"]
            invite_users_to_channel(cid, COMMON_USERS, token)

    print("\nFinished creating and populating channels.")


if __name__ == "__main__":
    # quando estiver tudo certo, só rodar:
    # create_all_channels()

    # exemplo de teste em um único canal
    token = os.getenv("SLACK_USER_TOKEN")
    res = create_slack_channel("bkr_development_novos-cores-gestão", token)
    if res.get("ok"):
        cid = res["channel"]["id"]
        invite_users_to_channel(cid, COMMON_USERS + [GESTAO_EXTRA_USER], token)
