"""Scraping and HTML/JSON cleaning utilities for job posting descriptions."""

import re
from bs4 import BeautifulSoup
import requests
from src.core.utils import setup_logger, clean_text, retry

logger = setup_logger("job_scraper")


class JobScraper:
    """Parses HTML/JSON content into clean text."""

    @staticmethod
    def parse_html_description(html_content: str) -> str:
        """Strip HTML tags, scripts, and styles, returning clean plain text."""
        if not html_content:
            return ""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Remove non-content elements
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()

            text = soup.get_text(separator=" ")
            return clean_text(text)
        except Exception as e:
            logger.warning(f"HTML parsing warning: {e}")
            return clean_text(html_content)

    @retry(max_retries=2, backoff_factor=1.5)
    def fetch_and_parse_url(self, url: str) -> str:
        """Fetch job page by URL and extract clean text description."""
        logger.info(f"Scraping job page URL: {url}")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return self.parse_html_description(response.text)
        except Exception as e:
            logger.error(f"Failed to scrape job URL {url}: {e}")
            return ""
