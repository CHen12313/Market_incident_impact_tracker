import requests
from bs4 import BeautifulSoup

HEADERS = {          # helps avoid 403 blocks
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115 Safari/537.36"
    )
}

URL = "https://www.morganstanley.com/insights/podcasts/thoughts-on-the-market"


def fetch_latest_transcript() -> str:
    """Return the transcript text of the newest ‘Thoughts on the Market’ episode."""
    page = requests.get(URL, headers=HEADERS, timeout=15)
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")

    # ----- Preferred path: grab the first transcript-container ----------------
    container = soup.select_one("div.transcript-container")
    if not container:                                # ----- Fallback ----------
        # find the first <h2> titled 'Transcript', then read following siblings
        title = soup.find("h2", string=lambda s: s and s.strip().lower() == "transcript")
        if not title:
            raise RuntimeError("No transcript found on page.")
        # collect paragraphs until the next heading/tag breaks the flow
        container = title.find_next_sibling()
        # if that node isn’t the paragraph wrapper, step into the next <div>
        if container.name != "div":
            container = container.find_next("div")

    # Pull text from <p> tags, collapse spacing, join with newlines
    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    return "\n".join(paragraphs)


if __name__ == "__main__":
    print(fetch_latest_transcript())
