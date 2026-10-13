from html.parser import HTMLParser
from urllib.parse import urljoin


INDICATOR_PHRASES = {
    "consent": (
        "before you continue",
        "we need your consent",
        "cookie consent",
        "manage your cookie preferences",
        "accept cookies",
    ),
    "captcha": ("captcha", "verify you are human", "security check"),
    "challenge": (
        "challenge",
        "unusual traffic",
        "access denied",
        "just a moment",
        "checking your browser",
        "enable javascript",
    ),
    "empty_results": ("no jobs found", "no results", "we couldn't find"),
}


class _HTMLNode:
    def __init__(self, tag="", attrs=None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children = []
        self.text = []

    def text_content(self):
        parts = list(self.text)
        for child in self.children:
            parts.append(child.text_content())
        return " ".join("".join(parts).split())

    def find_first(self, **attributes):
        if all(self.attrs.get(key) == value for key, value in attributes.items()):
            return self
        for child in self.children:
            match = child.find_first(**attributes)
            if match:
                return match
        return None

    def find_link(self):
        href = self.attrs.get("href", "")
        if "/job/" in href:
            return href
        for child in self.children:
            link = child.find_link()
            if link:
                return link
        return None

    def count_job_links(self):
        count = 1 if "/job/" in self.attrs.get("href", "") else 0
        return count + sum(child.count_job_links() for child in self.children)


class _SeekHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _HTMLNode("document")
        self.stack = [self.root]
        self.job_cards = []

    def handle_starttag(self, tag, attrs):
        node = _HTMLNode(tag, attrs)
        self.stack[-1].children.append(node)
        if "data-job-id" in node.attrs:
            self.job_cards.append(node)
        if tag not in {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr",
        }:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].text.append(data)


def collect_body_indicators(body_text, final_url=None, title=None):
    body_lower = (body_text or "").lower()
    url_lower = (final_url or "").lower()
    title_lower = (title or "").lower()
    signal_text = " ".join((body_lower, url_lower, title_lower))
    indicators = [
        name for name, phrases in INDICATOR_PHRASES.items()
        if any(phrase in signal_text for phrase in phrases)
    ]
    if (
        "consent" not in indicators
        and ("consent" in url_lower or "consent" in title_lower)
    ):
        indicators.append("consent")
    return indicators


def classify_page(
    card_count,
    job_link_count,
    body_indicators,
    response_status=None,
    source="browser",
    challenge_evidence=False,
):
    """Classify a page while retaining the legacy source-specific precedence."""
    if card_count:
        return "valid_listings"
    if (
        challenge_evidence
        or "captcha" in body_indicators
        or "challenge" in body_indicators
    ):
        return "bot_challenge"

    if source == "static":
        if "consent" in body_indicators:
            return "consent"
        if response_status is not None and not 200 <= response_status < 300:
            return "indeterminate"
        if "empty_results" in body_indicators:
            return "empty_results"
        return "indeterminate"

    if response_status is not None and not 200 <= response_status < 300:
        return "indeterminate"
    if "consent" in body_indicators:
        return "consent"
    if job_link_count:
        return "selector_mismatch"
    if "empty_results" in body_indicators:
        return "empty_results"
    return "indeterminate"


def parse_jobs_from_html(html, base_url="", response_status=None, title=None):
    """Return job dictionaries and a diagnostic from rendered Seek HTML."""
    html_parser = _SeekHTMLParser()
    html_parser.feed(html)
    jobs = []

    for card in html_parser.job_cards[:50]:
        job_id = card.attrs.get("data-job-id", "").strip()
        title_node = card.find_first(**{"data-automation": "jobTitle"})
        link = card.find_link()
        card_title = title_node.text_content() if title_node else ""
        if not job_id or not card_title or not link:
            continue

        def value_or_default(automation, default):
            node = card.find_first(**{"data-automation": automation})
            return node.text_content() if node else default

        jobs.append({
            "id": job_id,
            "title": card_title,
            "company": value_or_default("jobCompany", "N/A"),
            "salary": value_or_default("jobSalary", "Not specified"),
            "location": value_or_default("jobLocation", "Remote"),
            "posted_date": value_or_default("jobListedDate", "Recently"),
            "link": urljoin(base_url, link),
        })

    indicators = collect_body_indicators(
        html_parser.root.text_content(),
        final_url=base_url,
        title=title,
    )
    diagnostic = {
        "classification": classify_page(
            len(jobs),
            html_parser.root.count_job_links(),
            indicators,
            response_status=response_status,
            source="static",
        ),
        "final_url": base_url or None,
        "title": title,
        "response_status": response_status,
        "card_count": len(html_parser.job_cards),
        "job_link_count": html_parser.root.count_job_links(),
        "body_indicators": indicators,
    }
    return jobs, diagnostic