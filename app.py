import os
from urllib.error import HTTPError, URLError

import streamlit as st

from engine import DEFAULT_BOARDS, board_jobs, employer_queries, mentions, parse_boards, plan, profile, rank, search


st.set_page_config(page_title="JobScout", layout="wide")
st.title("JobScout")
st.write("Turn a résumé into targeted searches and see which skills match each result.")

with st.sidebar:
    st.header("Search settings")
    upload = st.file_uploader("Résumé PDF", type=["pdf"])
    mode = st.radio("Search sources", ["Employer boards (no API key)", "Direct employer postings via Brave", "General web search"])
    board_mode = mode == "Employer boards (no API key)"
    employer_only = mode == "Direct employer postings via Brave"
    if board_mode:
        board_field = st.text_input("Employer boards", DEFAULT_BOARDS, max_chars=1200)
        st.caption("Use provider:slug for Greenhouse, Lever, or Ashby boards. Only the board identifier goes to the provider.")
        location = st.text_input("Location filter (optional)", placeholder="Remote, Houston, or New York", max_chars=80)
        key = None
    else:
        location = st.text_input("Location or remote preference", "Remote US", max_chars=80)
        key = os.environ.get("BRAVE_SEARCH_API_KEY") or st.text_input("Brave Search API key", type="password")
        st.caption("The PDF is processed in this app. Only the displayed search strings go to Brave.")

if not upload:
    st.info("Upload a résumé PDF to start.")
    st.stop()

try:
    roles, skills = profile(upload.getvalue())
except ValueError as exc:
    st.error(str(exc))
    st.stop()

st.subheader("1. Review your search plan")
title_field = st.text_input("Target titles, comma-separated", ", ".join(roles), max_chars=250)
skill_field = st.text_input("Skills, comma-separated", ", ".join(skills), max_chars=450)
roles = [role.strip() for role in title_field.split(",") if role.strip()][:3]
skills = [skill.strip() for skill in skill_field.split(",") if skill.strip()][:20]
if not roles:
    st.info("Enter at least one target job title.")
    st.stop()

if board_mode:
    try:
        targets = parse_boards(board_field)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
else:
    targets = employer_queries(roles, location.strip()) if employer_only else plan(roles, skills, location.strip())
    for query in targets:
        st.code(query, language=None)

signature = (mode, tuple(targets), tuple(roles), tuple(skills), location.strip())
st.subheader("2. Search for jobs")
if not board_mode and not key:
    st.info("Add a Brave Search API key or switch to Employer boards.")
if st.button("Search jobs", type="primary", disabled=not (board_mode or key)):
    st.session_state.pop("results", None)
    hits, failures = [], []
    with st.spinner("Searching for matching roles…"):
        for target in targets:
            try:
                if board_mode:
                    hits.extend(
                        job for job in board_jobs(target)
                        if any(mentions(job["title"], role) for role in roles)
                        and (not location.strip() or location.strip().casefold() in job["location"].casefold())
                    )
                else:
                    hits.extend(search(target, key, employer_only))
            except HTTPError as exc:
                failures.append(f"{target} returned HTTP {exc.code}.")
                if not board_mode and exc.code in (401, 403, 429):
                    break
            except (URLError, TimeoutError, ValueError, KeyError, TypeError):
                failures.append(f"Could not read results from {target}.")
    st.session_state["results"] = (signature, rank(hits, roles, skills, employer_only), list(dict.fromkeys(failures)))

result = st.session_state.get("results")
if result and result[0] == signature:
    _, jobs, failures = result
    for failure in failures:
        st.warning(failure)
    if not jobs:
        st.info("No matches returned. Try a broader title, clear the location filter, or add more employer boards.")
    else:
        st.subheader(f"3. Review {len(jobs)} matches")
        st.caption("Ranked by title and skill mentions in available posting text. Check the listing for availability, work arrangement, and sponsorship.")
        for score, title, snippet, url, matches in jobs:
            with st.container(border=True):
                st.text(title or url)
                st.text(snippet)
                if matches:
                    st.caption("Matched skills: " + ", ".join(matches))
                st.link_button("Open employer posting" if employer_only or board_mode else "Open result", url)
