import os
import re
import json
import pathlib
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
import time 
import random

load_dotenv()

JIRA_BASE  = os.getenv("JIRA_BASE")   # ex: https://mblabs.atlassian.net
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")

if not (JIRA_BASE and JIRA_EMAIL and JIRA_TOKEN):
    raise SystemExit("Faltou configurar JIRA_BASE / JIRA_EMAIL / JIRA_TOKEN no .env")

AUTH = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)

HEADERS_JSON = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}
HEADERS_BIN = {"Accept": "*/*"}

OUT_DIR = pathlib.Path("jira_backup")
OUT_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}

# ========= CONFIG: 4 boards (nome + JQL do filtro do board) =========
BOARDS = [
    {"name": "Board 1 - EUR - Conta Digital", "jql": 'project = EUR AND issuetype != Bug AND "EUR-Funcionalidade[Dropdown]" NOT IN ("CARTÃO BENEFÍCIO", EMPRESTIMO, PIX, TECNOLOGIA) AND "EUR-Categoria[Select List (multiple choices)]" != INFRA ORDER BY Rank ASC'},
    {"name": "Board 2 - EUR - Empréstimos", "jql": 'project = EUR AND issuetype != Bug AND "EUR-Funcionalidade[Dropdown]" = EMPRESTIMO ORDER BY Rank ASC'},
    {"name": "Board 3 - EUR - PIX", "jql": 'project = EUR AND "EUR-Funcionalidade[Dropdown]" = PIX ORDER BY Rank ASC'},
    {"name": "Board 4 - EUR - Cartão Benefício", "jql": 'project = EUR AND issuetype != Bug AND "EUR-Funcionalidade[Dropdown]" = "CARTÃO BENEFÍCIO" ORDER BY Rank ASC'},
]

# Campos padrão (API names) + seus custom fields
FIELDS = [
    "summary",
    "description",
    "status",
    "parent",
    "assignee",
    "reporter",
    "priority",
    "timeoriginalestimate",
    "timetracking",
    "created",
    "updated",
    "duedate",
    "comment",
    "attachment",

    # custom fields
    "customfield_10532",
    "customfield_10529",
    "customfield_10630",
    "customfield_10632",
    "customfield_10631",
    "customfield_10582",
]

SESSION = requests.Session()
SESSION.auth = AUTH

def safe_name(s: str) -> str:
    s = re.sub(r"[^\w\-\.\(\)\[\] ]+", "_", s, flags=re.UNICODE)
    return s.strip()[:120] if s else "SEM_NOME"

def jira_post(path: str, body: dict, timeout=120) -> dict:
    url = f"{JIRA_BASE}{path}"
    r = SESSION.post(url, headers=HEADERS_JSON, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()

def download_file(url: str, dest: pathlib.Path, max_retries: int = 8):
    """
    Baixa anexos respeitando rate limit (429).
    - Usa Retry-After quando existir
    - Backoff exponencial com jitter
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_retries + 1):
        r = SESSION.get(url, headers=HEADERS_BIN, stream=True, timeout=180)

        # OK
        if r.status_code == 200:
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            return

        # Rate limit
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait_s = int(retry_after)
            else:
                # backoff exponencial: 2,4,8,16... + jitter
                wait_s = min(60, 2 ** attempt) + random.random()

            print(f"    429 ao baixar anexo. Tentativa {attempt}/{max_retries}. Aguardando {wait_s:.1f}s...")
            time.sleep(wait_s)
            continue

        # Outros erros: mostra detalhe e pula (não derruba o backup inteiro)
        try:
            body_preview = r.text[:300]
        except Exception:
            body_preview = "<sem body>"

        print(f"    ERRO {r.status_code} ao baixar {url} (tentativa {attempt}/{max_retries})")
        print(f"    Body (preview): {body_preview}")

        # Para 403/404 etc, não adianta insistir muito; quebra logo
        if r.status_code in (401, 403, 404):
            return

        # Para demais, tenta mais algumas vezes
        time.sleep(min(30, 2 ** attempt) + random.random())

    print(f"    Falhou após {max_retries} tentativas: {url}")

def fetch_all_issues_enhanced(jql: str, page_size=100):
    """
    Enhanced search (POST /rest/api/3/search/jql):
    pagina usando nextPageToken (não startAt).
    """
    all_issues = []
    next_token = None
    page = 0

    while True:
        page += 1
        body = {
            "jql": jql,
            "maxResults": page_size,
            "fields": FIELDS,
        }
        if next_token:
            body["nextPageToken"] = next_token

        data = jira_post("/rest/api/3/search/jql", body=body, timeout=180)

        issues = data.get("issues", []) or []
        all_issues.extend(issues)

        next_token = data.get("nextPageToken")  # se vier, tem próxima página
        print(f"  - página {page}: +{len(issues)} issues (acumulado={len(all_issues)}) token={'SIM' if next_token else 'NÃO'}")

        # Regra de parada: sem token = acabou (ou Atlassian resolveu devolver tudo numa página)
        if not next_token:
            break

        # Proteção anti-loop (nunca deveria acontecer)
        if page > 5000:
            raise RuntimeError("Paginação estourou 5000 páginas — algo errado com nextPageToken.")

    return all_issues

def main():
    import time
    import random

    manifest = {
        "jira_base": JIRA_BASE,
        "boards": [],
    }

    for b in BOARDS:
        board_name = b["name"]
        jql = b["jql"]

        board_dir = OUT_DIR / safe_name(board_name)
        board_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[{board_name}]")
        print(f"JQL: {jql}")

        issues = fetch_all_issues_enhanced(jql, page_size=100)
        print(f"[{board_name}] TOTAL baixado: {len(issues)}")

        board_index = {
            "board": board_name,
            "jql": jql,
            "total_issues": len(issues),
            "issues": [],
        }

        for issue in issues:
            key = issue.get("key")
            f = issue.get("fields", {}) or {}
            summary = f.get("summary", "")
            itype = (f.get("issuetype") or {}).get("name", "")
            status = (f.get("status") or {}).get("name", "")

            issue_folder = board_dir / safe_name(key)
            issue_folder.mkdir(parents=True, exist_ok=True)

            # 1) JSON bruto
            with open(issue_folder / "issue_raw.json", "w", encoding="utf-8") as fp:
                json.dump(issue, fp, ensure_ascii=False, indent=2)

            # 2) Imagens anexadas (com: skip se já existe + pausa leve + retry/backoff no download_file)
            attachments = f.get("attachment") or []
            img_dir = issue_folder / "imagens"
            saved = 0

            for att in attachments:
                mime = att.get("mimeType")
                if mime not in IMAGE_MIMES:
                    continue

                url = att.get("content")
                if not url:
                    continue

                filename = safe_name(att.get("filename", f"{key}_img"))
                dest_path = img_dir / filename

                # ✅ skip se já baixou antes (ótimo para retomar após erro)
                if dest_path.exists() and dest_path.stat().st_size > 0:
                    continue

                # ✅ pequena pausa para reduzir 429
                time.sleep(0.2 + random.random() * 0.3)  # 0.2 a 0.5s

                # ✅ baixa com retry/backoff (sua download_file deve estar com o tratamento de 429)
                try:
                    download_file(url, dest_path)
                    saved += 1
                except Exception as e:
                    # não derruba o backup inteiro por causa de 1 anexo
                    print(f"    Falha ao baixar anexo em {key}: {e}")

            board_index["issues"].append({
                "key": key,
                "summary": summary,
                "issuetype": itype,
                "status": status,
                "images_downloaded": saved,
                "folder": str(issue_folder.relative_to(OUT_DIR)),
            })

        # index.json do board
        with open(board_dir / "index.json", "w", encoding="utf-8") as fp:
            json.dump(board_index, fp, ensure_ascii=False, indent=2)

        manifest["boards"].append({
            "name": board_name,
            "folder": str(board_dir.relative_to(OUT_DIR)),
            "total_issues": len(issues),
            "index_file": str((board_dir / "index.json").relative_to(OUT_DIR)),
        })

        print(f"[{board_name}] OK -> {board_dir.resolve()}")

    # manifest geral
    with open(OUT_DIR / "backup_manifest.json", "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2)

    print(f"\nBackup final em: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
