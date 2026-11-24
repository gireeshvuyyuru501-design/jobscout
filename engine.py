"""Résumé extraction, search planning, and ranking for JobScout."""
import re
from html import unescape
from json import loads
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import fitz


SKILLS = (
    "Python", "SQL", "PySpark", "Databricks", "FastAPI", "LangGraph",
    "GraphRAG", "RAG", "Neo4j", "Cypher", "RDF", "OWL", "SHACL",
    "Azure", "AWS", "Kubernetes", "React", "Node.js", "Java", "Docker",
    "Power BI", "SAP", "Oracle", "Terraform", "Machine Learning",
)
ROLES = (
    "Lead AI Engineer", "Senior AI Engineer", "Generative AI Engineer",
    "AI/ML Engineer", "AI Engineer", "Machine Learning Engineer",
    "Data Engineer", "Data Scientist", "Backend Engineer",
    "Software Engineer", "Oracle Developer", "SAP Consultant",
    "Business Analyst", "Product Manager", "Registered Nurse",
)


def mentions(text, term):
    return bool(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I))


def profile(pdf):
    if not pdf or len(pdf) > 8_000_000:
        raise ValueError("Choose a PDF résumé under 8 MB.")
    try:
        with fitz.open(stream=pdf, filetype="pdf") as doc:
            if doc.is_encrypted or doc.page_count > 20:
                raise ValueError("Use an unlocked PDF with no more than 20 pages.")
            pages = [page.get_text() for page in doc]
    except (fitz.FileDataError, fitz.EmptyFileError) as exc:
        raise ValueError("This file could not be read as a PDF.") from exc
    text = "\n".join(pages).strip()
    if not text:
        raise ValueError("This PDF has no selectable text. Use a text-based résumé.")
    roles = []
    for role in ROLES:
        if mentions(text, role) and not any(mentions(other, role) for other in roles):
            roles.append(role)
    return roles[:5], [skill for skill in SKILLS if mentions(text, skill)]


def plan(roles, skills, location):
    return [
        " ".join(filter(None, [f'"{role}"', location,
                               skills[i % len(skills)] if skills else "", "jobs hiring"]))
        for i, role in enumerate(roles[:3])
    ]


# Public employer recruiting sites. The regexes distinguish individual jobs
# from the employer's board homepage.
JOB_PAGES = {
    "boards.greenhouse.io": r"/[^/]+/jobs/[0-9]+/?",
    "job-boards.greenhouse.io": r"/[^/]+/jobs/[0-9]+/?",
    "jobs.lever.co": r"/[^/]+/[0-9a-f-]{36}(?:/apply)?/?",
    "jobs.ashbyhq.com": r"/[^/]+/[0-9a-f-]{36}(?:/application)?/?",
}


def employer_queries(roles, location):
    sources = "(" + " OR ".join(f"site:{host}" for host in JOB_PAGES) + ")"
    return [f'"{role}" {location} {sources}' for role in roles[:3]]


def direct_job_key(parts):
    pattern = JOB_PAGES.get(parts.hostname)
    if not pattern or not re.fullmatch(pattern, parts.path, re.I):
        return None
    path = re.sub(r"/(?:apply|application)$", "", parts.path.rstrip("/"))
    host = "greenhouse" if parts.hostname.endswith(".greenhouse.io") else parts.hostname
    return host, path



def search(query, key, employer_only=False):
    params = {"q": query, "count": 10}
    if not employer_only:
        params["freshness"] = "pm"
    url = "https://api.search.brave.com/res/v1/web/search?" + urlencode(params)
    request = Request(url, headers={"Accept": "application/json", "X-Subscription-Token": key})
    with urlopen(request, timeout=15) as response:
        payload = loads(response.read())
    return payload.get("web", {}).get("results", [])


def rank(results, roles, skills, employer_only=False):
    unique = {}
    for row in results:
        url = row.get("url", "")
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            continue
        title = unescape(re.sub(r"<[^>]+>", "", row.get("title", "")))
        snippet = unescape(re.sub(r"<[^>]+>", "", row.get("description", "")))
        evidence = f"{title} {snippet}"
        if row.get("board"):
            snippet = f"{row['board']} · {row['location'] or 'Location not listed'}\n{snippet[:420]}"
        matches = [skill for skill in skills if mentions(evidence, skill)]
        score = 4 * any(mentions(title, role) for role in roles) + len(matches)
        if not score:
            continue
        direct_key = direct_job_key(parts)
        if employer_only and not direct_key:
            continue
        key = direct_key or (parts.hostname, parts.path.rstrip("/"), parts.query)
        candidate = (score, title, snippet, url, matches)
        if key not in unique or score > unique[key][0]:
            unique[key] = candidate
    return sorted(unique.values(), key=lambda row: -row[0])[:15]


DEFAULT_BOARDS = "greenhouse:anthropic, greenhouse:databricks"
BOARD_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
}


def parse_boards(value):
    boards = list(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))
    if not 1 <= len(boards) <= 10:
        raise ValueError("Enter 1 to 10 employer boards.")
    for board in boards:
        provider, _, slug = board.partition(":")
        if provider not in BOARD_ENDPOINTS or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", slug):
            raise ValueError(f"Invalid board {board!r}. Use provider:slug, such as ashby:openai.")
    return boards


def board_jobs(board):
    provider, slug = board.split(":", 1)
    request = Request(BOARD_ENDPOINTS[provider].format(slug), headers={"Accept": "application/json"})
    with urlopen(request, timeout=8) as response:
        payload = loads(response.read())
    rows = payload if provider == "lever" else payload["jobs"]
    for row in rows:
        if provider == "greenhouse":
            title, url = row["title"], row["absolute_url"]
            location = (row.get("location") or {}).get("name", "")
            description = row.get("content") or ""
        elif provider == "lever":
            title, url = row["text"], row["hostedUrl"]
            location = (row.get("categories") or {}).get("location", "")
            description = row.get("descriptionPlain") or ""
        else:
            if row.get("isListed") is False:
                continue
            title, url = row["title"], row["jobUrl"]
            location = row.get("location") or ""
            if row.get("isRemote") or row.get("workplaceType") == "Remote":
                location = f"Remote · {location}"
            description = row.get("descriptionPlain") or ""
        summary = " ".join(re.sub(r"<[^>]+>", " ", unescape(description)).split())
        yield {"title": title, "url": url, "description": summary, "location": location, "board": board}
