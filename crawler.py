import scrapy
import pdfplumber
from PIL import Image
import pytesseract
from io import BytesIO
import re
from urllib.parse import urlparse


# ---------- Pipeline ----------
class TextFilePipeline:
    def open_spider(self, spider):
        self.file = open('crawled_data.txt', 'w', encoding='utf-8')
        self.file.write("Crawled Data from fmuniversity.nic.in\n")
        self.file.write("=" * 50 + "\n")
        self.file.flush()

    def close_spider(self, spider):
        self.file.close()

    def process_item(self, item, spider):
        url = item.get('url', '')
        ctype = item.get('content_type', '').upper()
        text = item.get('text', '') or "[NO TEXT]"

        self.file.write(f"\n=== {url} ===\n")
        self.file.write(f"TYPE: {ctype}\n")
        self.file.write("CONTENT:\n")
        self.file.write(text)
        self.file.write("\n" + "=" * 50 + "\n")
        self.file.flush()
        return item


# ---------- Item ----------
class PageItem(scrapy.Item):
    url = scrapy.Field()
    content_type = scrapy.Field()
    text = scrapy.Field()


# ---------- Spider ----------
class FMUSpider(scrapy.Spider):
    name = "fmu"
    allowed_domains = ["fmuniversity.nic.in"]
    start_urls = ["https://fmuniversity.nic.in/index"]

    custom_settings = {
        'ROBOTSTXT_OBEY': True,
        'CONCURRENT_REQUESTS': 8,
        'DOWNLOAD_DELAY': 1,
        'LOG_LEVEL': 'INFO',
        'ITEM_PIPELINES': {'__main__.TextFilePipeline': 300},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processed_urls = set()

    def normalise_url(self, url):
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip('/')

    def is_allowed(self, url):
        parsed = urlparse(url)
        domain = parsed.netloc
        return any(domain == d or domain.endswith('.' + d) for d in self.allowed_domains)

    def clean_text(self, text):
        return re.sub(r'\s+', ' ', text).strip()

    def parse(self, response):
        norm_url = self.normalise_url(response.url)
        if norm_url in self.processed_urls:
            return
        self.processed_urls.add(norm_url)

        ctype_header = response.headers.get('Content-Type', b'').decode().lower()

        # ---------- HTML ----------
        if 'text/html' in ctype_header:
            text_nodes = response.xpath('//body//text()[not(ancestor::script) and not(ancestor::style)]').getall()
            text = self.clean_text(' '.join(text_nodes))
            yield PageItem(url=response.url, content_type='html', text=text)

            for href in response.css('a::attr(href)').getall():
                url = response.urljoin(href)
                norm_link = self.normalise_url(url)
                if self.is_allowed(norm_link) and norm_link not in self.processed_urls:
                    yield scrapy.Request(norm_link, callback=self.parse)

        # ---------- PDF ----------
        elif 'application/pdf' in ctype_header or response.url.lower().endswith('.pdf'):
            try:
                with pdfplumber.open(BytesIO(response.body)) as pdf:
                    page_texts = [page.extract_text() or '' for page in pdf.pages]
                    text = self.clean_text('\n'.join(page_texts))
            except Exception as e:
                self.logger.warning(f"Failed to process PDF {response.url}: {e}")
                text = ""
            yield PageItem(url=response.url, content_type='pdf', text=text)

        # ---------- IMAGE ----------
        elif 'image/' in ctype_header or re.search(r'\.(jpg|jpeg|png|webp|bmp|gif)$', response.url.lower()):
            try:
                img = Image.open(BytesIO(response.body))
                text = pytesseract.image_to_string(img)
                text = self.clean_text(text)
            except Exception as e:
                self.logger.warning(f"Failed to process image {response.url}: {e}")
                text = ""
            yield PageItem(url=response.url, content_type='image', text=text)

        else:
            self.logger.debug(f"Skipping unsupported content type: {response.url}")
