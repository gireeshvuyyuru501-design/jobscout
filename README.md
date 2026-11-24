# JobScout

Match a résumé PDF to public job postings from employer career boards.

## Run on Windows

Open this folder in VS Code and run:

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m streamlit run app.py
```

Upload a text-based résumé PDF, review the detected titles and skills, and select **Search jobs**. The optional location filter matches text in the listed location.

## Search sources

- **Employer boards (no API key)** reads public Greenhouse, Lever, and Ashby feeds. The default boards are Anthropic and Databricks. Add other boards as comma-separated `provider:slug` entries.
- **Brave web search** is optional and requires a Brave Search API key. Use the password field or set `BRAVE_SEARCH_API_KEY`.

## How matching works

PyMuPDF extracts the text locally. JobScout filters employer-board results by title and optional location, then ranks them by title and skill mentions. Each result links to the employer posting. Check the original description for eligibility and sponsorship.

The résumé stays local. Employer-board requests send the board identifier. Brave mode sends the search strings displayed in the app.

**Stack:** Python, Streamlit, PyMuPDF, Greenhouse, Lever, Ashby, and optional Brave Search.

## License

[MIT](LICENSE)
