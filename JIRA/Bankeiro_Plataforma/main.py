import time
import os
import requests
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ========= Jira (Cloud) =========
JIRA_BASE = os.getenv("JIRA_BASE", "https://bankeirobrasil.atlassian.net")
JIRA_AUTH_HEADER = os.environ["JIRA_AUTH_HEADER"]
JIRA_HEADERS = {
    "Accept": "application/json",
    "Authorization": JIRA_AUTH_HEADER,
}

# ========= Slack =========
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

FIELD_NAME = "Bankeiro Team"
FIELD_KEY = 'customfield_11404'

JQL_DOWNSTREAM = (
    'project=PLTF AND issuetype in (Story, "Incident (PRD)", Kaizen) '
    'AND status in (Comprometido, "REF. SQUAD", Develop, "Para Teste", Teste, "Ready Release")'
)

JQL_UPSTREAM = (
    'project=PLTF AND issuetype in (Story, "Incident (PRD)", Kaizen) '
    'AND status in (Backlog, "REF. FUNCIONAL", "REF. TÉCNICO", "Pronto p/ Comprometimento")'
)

JQL_SPECIAL_ISSUES = (
    "project=PLTF AND issuetype in (Pendência, Risco, Problema) and statusCategory != Done"
)

JQL_INCIDENTS = (
    'project=PLTF AND issuetype = "Incident (PRD)" '
    'AND status in (Comprometido, "REF. SQUAD", Develop, "Para Teste", Teste, "Ready Release")'
)

VALUES = [
    'Adquirência', 'Autorizadores', 'Benefícios', 'Caixinha', 'Cartão', 'Conta',
    'Crédito', 'Investimento', 'Misc', 'Novos Cores', 'Onboarding',
    'Regulatório', 'Transacional'
]


def fetch_counts_by_team(base_jql: str) -> tuple[dict, int]:
    """
    Faz UMA chamada pro JQL base e retorna:
      - dict { "Nome do Time": quantidade }
      - total de issues nesse JQL
    """
    url = f"{JIRA_BASE}/rest/api/3/search/jql"
    params = {
        "jql": base_jql,
        "maxResults": 5000,        # limite alto, 1 página
        "fields": FIELD_KEY        # só traz o campo Bankeiro Team
    }

    response = requests.get(url, params=params, headers=JIRA_HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()

    # garante que todos os VALUES existem na dict, mesmo se 0
    counts = {team: 0 for team in VALUES}

    for issue in data.get("issues", []):
        fields = issue.get("fields", {})
        team_field = fields.get(FIELD_KEY)

        # multiselect: normalmente é uma lista de opções
        team_name = None
        if isinstance(team_field, list):
            if team_field:
                team_name = team_field[0].get("value") or team_field[0].get("name")
        elif isinstance(team_field, dict):
            team_name = team_field.get("value") or team_field.get("name")

        if team_name and team_name in counts:
            counts[team_name] += 1

    total = sum(counts.values())
    return counts, total

def post_slack(text: str, blocks=None):
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=30)
    r.raise_for_status()


def build_slack_blocks(rows, total_downstream, total_upstream, total_special):
    # rows = [(value, downstream_total, upstream_count, special_count, incidents_count), ...]
    # ordenar por downstream_total (index 1)
    rows_sorted = sorted(rows, key=lambda x: x[1], reverse=True)

    # Times que vão pro bloco principal: têm algum downstream OU algum especial OU algum incident
    display_rows = [
        (value, downstream_total, upstream_count, special_count, incidents_count)
        for value, downstream_total, upstream_count, special_count, incidents_count in rows_sorted
        if downstream_total > 0 or special_count > 0 or incidents_count > 0
    ]

    # Listas em ordem alfabética
    zero_downstream_values = sorted([
        value
        for value, downstream_total, upstream_count, special_count, incidents_count in rows_sorted
        if downstream_total == 0
    ])

    zero_special_values = sorted([
        value
        for value, downstream_total, upstream_count, special_count, incidents_count in rows_sorted
        if special_count == 0
    ])

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Visão Geral de Issues por Time Bankeiro"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "<https://bankeirobrasil.atlassian.net/jira/software/c/projects/PLTF/boards/1798|Abrir Jira>"
                }
            ]
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Total em Upstream:* *{total_upstream}*"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Total em Downstream:* *{total_downstream}*"
                }
            ]
        },
        {"type": "divider"}
    ]

    # Cada linha = 1 section, com até 2 colunas
    for i in range(0, len(display_rows), 2):
        chunk = display_rows[i:i+2]
        fields = []
        for value, downstream_total, upstream_count, special_count, incidents_count in chunk:
            # Itens normais = downstream_total - incidents
            itens_count = max(downstream_total - incidents_count, 0)
            fields.append({
                "type": "mrkdwn",
                "text": (
                    f"*{value}*\n"
                    f"`{itens_count}` Itens\n"
                    f"`{incidents_count}` Incidentes\n"
                    f"`{special_count}` Issues Especiais"
                )
            })
        blocks.append({
            "type": "section",
            "fields": fields
        })

    if zero_downstream_values or zero_special_values:
        blocks.append({"type": "divider"})

    if zero_downstream_values:
        zeros_downstream_text = ", ".join(zero_downstream_values)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Sem issues em downstream:*\n{zeros_downstream_text}"
            }
        })

    if zero_special_values:
        zeros_special_text = ", ".join(zero_special_values)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Sem issues especiais:*\n{zeros_special_text}"
            }
        })

    return blocks

def main():
    # 4 chamadas no total, uma por JQL
    downstream_counts, total_downstream = fetch_counts_by_team(JQL_DOWNSTREAM)
    upstream_counts, total_upstream = fetch_counts_by_team(JQL_UPSTREAM)
    special_counts, total_special = fetch_counts_by_team(JQL_SPECIAL_ISSUES)
    incidents_counts, total_incidents = fetch_counts_by_team(JQL_INCIDENTS)

    rows = []
    for value in VALUES:
        downstream_total = downstream_counts.get(value, 0)
        upstream_count = upstream_counts.get(value, 0)
        special_count = special_counts.get(value, 0)
        incidents_count = incidents_counts.get(value, 0)

        rows.append((value, downstream_total, upstream_count, special_count, incidents_count))

    blocks = build_slack_blocks(rows, total_downstream, total_upstream, total_special)

    fallback_text = (
        f"Visão geral por {FIELD_NAME} – "
        f"Downstream: {total_downstream}, Upstream: {total_upstream}, "
        f"Especiais: {total_special}"
    )

    post_slack(text=fallback_text, blocks=blocks)



if __name__ == "__main__":
    main()