import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse


def read_webpage(url: str) -> str:
    """
    Retrieve a webpage and extract its readable text.

    Args:
        url: URL of the webpage to read.

    Returns:
        str: Extracted webpage text.
    """
    url = url.strip()

    if not url:
        raise ValueError("The URL cannot be empty.")

    # Validate the URL
    parsed_url = urlparse(url)

    if parsed_url.scheme not in ("http", "https") or not parsed_url.hostname:
        raise ValueError("Invalid URL. An HTTP or HTTPS URL is required.")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; Sensai/1.0; "
            "+https://example.com/bot)"
        )
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=15,
            allow_redirects=True,
        )
        response.raise_for_status()

    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to retrieve webpage: {exc}") from exc

    # Parse the HTML
    soup = BeautifulSoup(response.text, "html.parser")

    # Remove elements that do not contain useful page content
    for element in soup(
        ["script", "style", "noscript", "svg", "iframe", "nav", "footer"]
    ):
        element.decompose()

    # Prefer the main content when available
    main_content = soup.find("main") or soup.find("article") or soup.body

    if main_content is None:
        return ""

    text = main_content.get_text(separator="\n", strip=True)

    # Clean up empty lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    return "\n".join(lines)