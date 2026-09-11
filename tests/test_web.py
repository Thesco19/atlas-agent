"""Unit tests for web tools (DuckDuckGo and fetch)."""
import unittest
from atlas_agent.tools import web

class TestWebTools(unittest.TestCase):
    def test_html_text_extractor(self):
        html_input = """
        <html>
            <head><title>Ignored</title></head>
            <body>
                <h1>Título do Artigo</h1>
                <p>Este é o primeiro parágrafo com texto real.</p>
                <script>console.log('ignored');</script>
                <style>.ignored { color: red; }</style>
                <div>Segundo bloco de texto.</div>
            </body>
        </html>
        """
        parser = web.HTMLTextExtractor()
        parser.feed(html_input)
        text = parser.get_text()

        self.assertIn("Título do Artigo", text)
        self.assertIn("Este é o primeiro parágrafo", text)
        self.assertIn("Segundo bloco de texto", text)
        self.assertNotIn("console.log", text)
        self.assertNotIn(".ignored", text)

    def test_duckduckgo_parser(self):
        sample_ddg_html = """
        <div class="result results_links results_links_deep web-result">
            <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpython.org">python.org</a>
            <h2 class="result__title">
                <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpython.org">Welcome to Python.org</a>
            </h2>
            <a class="result__snippet">The official home of the Python Programming Language.</a>
        </div>
        """
        parser = web.DuckDuckGoParser(max_results=2)
        parser.feed(sample_ddg_html)
        self.assertEqual(len(parser.results), 1)
        self.assertIn("Python.org", parser.results[0]["title"])
        self.assertEqual("https://python.org", parser.results[0]["url"])
        self.assertIn("official home", parser.results[0]["snippet"])

if __name__ == "__main__":
    unittest.main()
