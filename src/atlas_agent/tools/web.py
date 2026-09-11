"""Web tools: DuckDuckGo search and HTTP fetch using Python standard library."""
from __future__ import annotations
import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0"

class HTMLTextExtractor(HTMLParser):
    """Extract readable text content from HTML, skipping scripts and styles."""
    def __init__(self):
        super().__init__()
        self.result: List[str] = []
        self._skip_depth = 0
        self._skip_tags = {"script", "style", "noscript", "svg", "head"}

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]):
        tag_lower = tag.lower()
        if tag_lower in self._skip_tags:
            self._skip_depth += 1
        elif tag_lower in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.result.append("\n")

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in self._skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag_lower in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.result.append("\n")

    def handle_data(self, data: str):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self.result.append(f" {text} ")

    def get_text(self) -> str:
        raw = "".join(self.result)
        # Normalize whitespace and blank lines
        clean = re.sub(r"[ \t]+", " ", raw)
        clean = re.sub(r"\n\s*\n+", "\n\n", clean)
        return clean.strip()

def fetch_url(url: str, max_chars: int = 6000, timeout: int = 15) -> str:
    """Fetch URL and return clean text content."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw_bytes = resp.read(1024 * 512)  # Read up to 512 KB
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()

            try:
                decoded = raw_bytes.decode(charset, errors="replace")
            except Exception:
                decoded = raw_bytes.decode("utf-8", errors="replace")

            # If JSON, format nicely
            if "application/json" in content_type:
                try:
                    obj = json.loads(decoded)
                    formatted = json.dumps(obj, indent=2, ensure_ascii=False)
                    return formatted[:max_chars]
                except Exception:
                    return decoded[:max_chars]

            # If HTML, extract clean text
            if "text/html" in content_type or "<html" in decoded.lower():
                parser = HTMLTextExtractor()
                parser.feed(decoded)
                text = parser.get_text()
            else:
                text = decoded

            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n... (conteúdo truncado em {max_chars} caracteres)"

            return f"=== Conteúdo de {url} ===\n\n{text}"
    except Exception as e:
        return f"Erro ao acessar '{url}': {e}"

class DuckDuckGoParser(HTMLParser):
    """Parse search results from DuckDuckGo HTML endpoint."""
    def __init__(self, max_results: int = 5):
        super().__init__()
        self.max_results = max_results
        self.results: List[Dict[str, str]] = []
        self._in_result = False
        self._in_title = False
        self._in_snippet = False
        self._current_title: List[str] = []
        self._current_snippet: List[str] = []
        self._current_url = ""

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]):
        attr_dict = {k: v or "" for k, v in attrs}
        cls = attr_dict.get("class", "")

        if tag == "div" and ("result" in cls or "links_main" in cls):
            self._in_result = True

        if self._in_result:
            if tag == "a" and ("result__a" in cls or "result__url" in cls or "result-link" in cls):
                self._in_title = True
                href = attr_dict.get("href", "")
                if "uddg=" in href:
                    # Extract real url from uddg parameter
                    match = re.search(r"uddg=([^&]+)", href)
                    if match:
                        self._current_url = urllib.parse.unquote(match.group(1))
                    else:
                        self._current_url = href
                else:
                    self._current_url = href

            elif tag in ("a", "div", "span") and ("result__snippet" in cls or "snippet" in cls):
                self._in_snippet = True

    def handle_endtag(self, tag: str):
        if tag == "a" and self._in_title:
            self._in_title = False

        if self._in_snippet and tag in ("a", "div", "span", "p"):
            self._in_snippet = False
            # Save result if we have title & snippet or url
            title = "".join(self._current_title).strip()
            snippet = "".join(self._current_snippet).strip()
            if (title or snippet) and self._current_url and len(self.results) < self.max_results:
                self.results.append({
                    "title": title or "Sem título",
                    "url": self._current_url,
                    "snippet": snippet
                })
                self._current_title = []
                self._current_snippet = []
                self._current_url = ""
                self._in_result = False

    def handle_data(self, data: str):
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._current_snippet.append(data)

def duckduckgo_search(query: str, max_results: int = 5, timeout: int = 15) -> str:
    """Perform a web search using DuckDuckGo HTML / Instant Answer without API keys."""
    query = query.strip()
    if not query:
        return "Erro: Termo de busca vazio."

    # 1. First try DuckDuckGo Instant Answer API for quick factual / summary answers
    api_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            abstract = data.get("AbstractText", "")
            source_url = data.get("AbstractURL", "")
            related = data.get("RelatedTopics", [])

            instant_results: List[str] = []
            if abstract:
                instant_results.append(f"📌 Resumo direto:\n{abstract}\nFonte: {source_url}\n")

            if related:
                for item in related[:max_results]:
                    if isinstance(item, dict) and "Text" in item and "FirstURL" in item:
                        instant_results.append(f"• {item['Text']}\n  Link: {item['FirstURL']}")

            if instant_results:
                return f"Resultados DuckDuckGo para '{query}':\n\n" + "\n\n".join(instant_results)
    except Exception:
        pass

    # 2. Query DuckDuckGo HTML Lite for rich search results
    html_url = "https://html.duckduckgo.com/html/"
    post_data = urllib.parse.urlencode({"q": query}).encode("utf-8")
    req = urllib.request.Request(html_url, data=post_data, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            parser = DuckDuckGoParser(max_results=max_results)
            parser.feed(content)

            if not parser.results:
                # Regex fallback if HTML structure varied
                matches = re.findall(
                    r'<a[^>]+class="result__snippet[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    content,
                    re.IGNORECASE | re.DOTALL
                )
                if not matches:
                    return f"Nenhum resultado encontrado no DuckDuckGo para '{query}'."

            output_lines = [f"Resultados de busca DuckDuckGo para '{query}':\n"]
            for idx, item in enumerate(parser.results, 1):
                clean_snippet = html.unescape(item['snippet'])
                clean_title = html.unescape(item['title'])
                output_lines.append(f"{idx}. {clean_title}")
                output_lines.append(f"   URL: {item['url']}")
                if clean_snippet:
                    output_lines.append(f"   {clean_snippet}")
                output_lines.append("")

            return "\n".join(output_lines).strip()
    except Exception as e:
        return f"Erro ao realizar busca no DuckDuckGo: {e}"
