"""Pure parsing helpers for the keyless and API search providers."""

import base64
import binascii
import html
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlsplit


SEARCH_STOPWORDS = frozenset({
    "che", "chi", "come", "con", "cosa", "del", "dei", "della", "delle",
    "degli", "dove", "gli", "per", "perche", "perché", "quale", "quando",
    "sono", "una", "uno", "the", "and", "for", "what", "when", "where",
    "who", "with",
})


class DuckDuckGoParser(HTMLParser):
    """Extract organic links and snippets from DuckDuckGo's HTML page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self._current = None
        self._in_title = False
        self._in_snippet = False

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attributes = dict(attrs)
        classes = attributes.get("class", "").split()
        if "result__a" in classes:
            self._current = {
                "title": "",
                "url": attributes.get("href", ""),
                "snippet": "",
            }
            self._in_title = True
        elif "result__snippet" in classes and self.results:
            self._in_snippet = True

    def handle_endtag(self, tag):
        if tag != "a":
            return
        if self._in_title and self._current is not None:
            self.results.append(self._current)
            self._current = None
            self._in_title = False
        elif self._in_snippet:
            self._in_snippet = False

    def handle_data(self, data):
        if self._in_title and self._current is not None:
            self._current["title"] += data
        elif self._in_snippet and self.results:
            self.results[-1]["snippet"] += data


class BingParser(HTMLParser):
    """Extract title, link and snippet from Bing's result blocks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self._current = None
        self._depth = 0
        self._in_heading = False
        self._in_title = False
        self._in_snippet = False

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            if self._current is not None:
                self._depth += 1
            elif "b_algo" in (dict(attrs).get("class") or "").split():
                self._current = {"title": "", "url": "", "snippet": ""}
                self._depth = 0
            return
        if self._current is None:
            return
        if tag == "h2":
            self._in_heading = True
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            if not href:
                return
            if self._in_heading:
                # The heading link is the result: drop any site name or
                # breadcrumb captured from the smaller links before it.
                self._current["url"] = href
                self._current["title"] = ""
                self._in_title = True
            elif not self._current["url"]:
                self._current["url"] = href
                self._in_title = True
        elif tag == "p" and self._current["url"] and not self._current["snippet"]:
            self._in_snippet = True

    def handle_endtag(self, tag):
        if tag == "li":
            if self._current is None:
                return
            if self._depth:
                self._depth -= 1
            else:
                self.results.append(self._current)
                self._current = None
                self._in_title = False
                self._in_snippet = False
        elif tag in {"a", "h2"}:
            self._in_title = False
            if tag == "h2":
                self._in_heading = False
        elif tag == "p":
            self._in_snippet = False

    def handle_data(self, data):
        if self._current is None:
            return
        if self._in_title:
            self._current["title"] += data
        elif self._in_snippet:
            self._current["snippet"] += data


def normalize_search_result(title, url, snippet):
    if not isinstance(url, str):
        return None
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        return None
    clean_title = re.sub(r"\s+", " ", title).strip() if isinstance(title, str) else ""
    clean_snippet = (
        re.sub(r"\s+", " ", snippet).strip() if isinstance(snippet, str) else ""
    )
    return {
        "title": (clean_title or clean_url)[:200],
        "url": clean_url[:500],
        "snippet": clean_snippet[:500],
    }


def search_query_tokens(query):
    """Significant words used to check that results answer the query."""
    tokens = re.findall(r"[0-9a-zà-ÿ]+", query.lower())
    return [
        token for token in tokens
        if len(token) > 2 and token not in SEARCH_STOPWORDS
    ]


def results_match_query(results, query):
    """Reject pages an engine serves for a different query.

    Bing sometimes answers a query with no results using cached results for
    unrelated searches, so an empty page is safer than wrong data.
    """
    tokens = search_query_tokens(query)
    if not tokens:
        return True
    haystack = " ".join(
        f'{item["title"]} {item["snippet"]} {item["url"]}'
        for item in results
    ).lower()
    return any(token in haystack for token in tokens)


def duckduckgo_target(url):
    if not isinstance(url, str):
        return None
    target = url.strip()
    if target.startswith("//"):
        target = "https:" + target
    elif target.startswith("/l/"):
        target = "https://duckduckgo.com" + target
    parsed = urlsplit(target)
    if (
        parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com"}
        and parsed.path.startswith("/l/")
    ):
        redirect = parse_qs(parsed.query).get("uddg")
        if redirect:
            target = unquote(redirect[0])
    if not target.startswith(("http://", "https://")):
        return None
    return target


def bing_target(url):
    """Resolve the real destination of a Bing result link."""
    if not isinstance(url, str):
        return None
    target = url.strip()
    if target.startswith("//"):
        target = "https:" + target
    parsed = urlsplit(target)
    if parsed.hostname in {"bing.com", "www.bing.com"}:
        redirect = parse_qs(parsed.query).get("u", [""])[0]
        if redirect.startswith("a1"):
            encoded = redirect[2:]
            encoded += "=" * (-len(encoded) % 4)
            try:
                decoded = base64.urlsafe_b64decode(encoded).decode("utf-8")
            except (ValueError, binascii.Error, UnicodeDecodeError):
                return None
            if decoded.startswith(("http://", "https://")):
                return decoded
        return None
    if not target.startswith(("http://", "https://")):
        return None
    return target


def bing_html_results(page, num_results):
    parser = BingParser()
    parser.feed(page)
    results = []
    seen = set()
    for item in parser.results:
        result = normalize_search_result(
            item.get("title"), bing_target(item.get("url")), item.get("snippet"),
        )
        if result and result["url"] not in seen:
            seen.add(result["url"])
            results.append(result)
        if len(results) >= num_results:
            break
    return results


def bing_rss_results(page, num_results):
    try:
        root = ET.fromstring(page)
    except ET.ParseError:
        raise RuntimeError("Bing ha restituito una risposta non valida.") from None
    results = []
    seen = set()
    for item in root.iter("item"):
        description = item.findtext("description") or ""
        snippet = html.unescape(re.sub(r"<[^>]+>", " ", description))
        result = normalize_search_result(
            item.findtext("title") or "",
            (item.findtext("link") or "").strip(),
            snippet,
        )
        if result and result["url"] not in seen:
            seen.add(result["url"])
            results.append(result)
        if len(results) >= num_results:
            break
    return results


def yahoo_target(url):
    """Resolve the real destination of a Yahoo result link."""
    if not isinstance(url, str):
        return None
    target = url.strip()
    if target.startswith("//"):
        target = "https:" + target
    if not target.startswith(("http://", "https://")):
        return None
    parsed = urlsplit(target)
    if (parsed.hostname or "").endswith("search.yahoo.com"):
        redirect = re.search(r"/RU=(.*?)/RK=", parsed.path)
        if not redirect:
            return None
        target = unquote(redirect.group(1))
    if not target.startswith(("http://", "https://")):
        return None
    return target


def yahoo_results(page, num_results):
    """Extract organic results from Yahoo's server-rendered result page."""
    starts = [
        match.start()
        for match in re.finditer(r'<div class="dd algo[^"]*"', page)
    ]
    results = []
    seen = set()
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(page)
        block = page[start:end]
        title_match = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.S)
        if not title_match:
            continue
        title = html.unescape(re.sub(r"<[^>]+>", " ", title_match.group(1)))
        link_match = re.search(r'href="(https?://[^"]+)"', block)
        target = yahoo_target(link_match.group(1)) if link_match else None
        snippet = ""
        snippet_match = re.search(
            r'<div class="compText[^"]*"[^>]*>(.*?)</div>', block, re.S
        )
        if snippet_match:
            snippet = html.unescape(
                re.sub(r"<[^>]+>", " ", snippet_match.group(1))
            )
        result = normalize_search_result(title, target, snippet)
        if result and result["url"] not in seen:
            seen.add(result["url"])
            results.append(result)
        if len(results) >= num_results:
            break
    return results
