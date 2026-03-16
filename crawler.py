# crawler.py
import os
import re
import time
import requests
import io
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
import pdfplumber
from PIL import Image
import pytesseract
from pathlib import Path
import tqdm

# === CONFIGURATION ===
BASE_URL = "https://fmuniversity.nic.in/index"
MAX_DEPTH = 3
DELAY=1.0
OUTPUT_DIR = Path("output")
MAX_PAGES = 500

OUTPUT_DIR.mkdir(exist_ok=True)

# Set Tesseract path (for GitHub Actions)
os.environ["TESSDATA_PREFIX"] = "/usr/share/tesseract-ocr/4.00/tessdata"

# === HELPER FUNCTIONS ===
def is_valid_url(url):
    parsed = urlparse(url)
    return bool(parsed.netloc) and parsed.scheme in ("http", "https")

def normalize_url(url):
    url = re.split(r'[#?]', url)[0]
    if url.endswith('/'):
        url = url[:-1]
    return url

def get_file_extension(url):
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext

def safe_filename(url):
    name = re.sub(r'[<>:"|?*\\]', '_', urlparse(url).path.strip('/'))
    return (name or "index") + ".txt"

def download_file(url, timeout=10):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"❌ Failed to download {url}: {e}")
        return None

def extract_text_from_pdf(content):
    text = ""
    try:
        reader = PdfReader(io.BytesIO(content))
        for page in reader.pages:
            txt = page.extract_text()
            if txt:
                text += txt + "\n"
    except Exception:
        pass
    if not text.strip():
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    txt = page.extract_text()
                    if txt:
                        text += txt + "\n"
        except Exception as e:
            print(f"⚠️ PDF fallback failed: {e}")
    return text.strip()

def extract_text_from_image(content):
    try:
        img = Image.open(io.BytesIO(content))
        img = img.convert("L")
        text = pytesseract.image_to_string(img, lang='eng')
        return text.strip()
    except Exception as e:
        print(f"⚠️ OCR failed: {e}")
        return ""

# === MAIN CRAWLER ===
class UniversityCrawler:
    def __init__(self):
        self.visited = set()
        self.to_visit = [(BASE_URL, 0)]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; FMU-Crawler/1.0; +https://github.com/yourname/fmuniversity-crawler)"
        })

    def crawl(self):        pbar = tqdm.tqdm(total=MAX_PAGES, desc="Crawling")
        while self.to_visit and len(self.visited) < MAX_PAGES:
            url, depth = self.to_visit.pop(0)
            normalized = normalize_url(url)

            if normalized in self.visited or depth > MAX_DEPTH:
                continue

            self.visited.add(normalized)
            pbar.update(1)

            print(f"\n🔍 Crawling: {normalized} (depth={depth})")
            time.sleep(DELAY)

            content = download_file(normalized)
            if not content:
                continue

            ext = get_file_extension(normalized)
            file_path = OUTPUT_DIR / safe_filename(normalized)

            if ext in ['.pdf']:
                text = extract_text_from_pdf(content)
                self._save_text(text, file_path, normalized)
            elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                text = extract_text_from_image(content)
                self._save_text(text, file_path, normalized)
            else:
                # HTML
                try:
                    soup = BeautifulSoup(content, 'html.parser')
                    for tag in soup(['script', 'style']):
                        tag.decompose()
                    text = soup.get_text(separator="\n", strip=True)
                    self._save_text(text, file_path, normalized)
                except Exception as e:
                    print(f"⚠️ HTML parse error: {e}")

            # Extract links only for HTML pages
            if ext == '':
                try:
                    soup = BeautifulSoup(content, 'html.parser')
                    links = soup.find_all('a', href=True)
                    for link in links:
                        href = link['href']
                        full_url = urljoin(normalized, href)  # ✅ Correctly placed
                        if is_valid_url(full_url) and BASE_URL in full_url:
                            full_norm = normalize_url(full_url)
                            if full_norm not::  # ← THIS WAS THE BUG! (typo: :: instead of in)
                                if full_norm not in self.visited and len(self.to_visit) < MAX_PAGES:                                    self.to_visit.append((full_norm, depth + 1))
                except Exception as e:
                    print(f"⚠️ Link extraction error: {e}")

        pbar.close()
        print(f"\n✅ Crawled {len(self.visited)} pages.")

    def _save_text(self, text, filepath, url):
        header = f"URL: {url}\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n{'='*50}\n\n"
        full_text = header + (text or "[No extractable text]")
        filepath.write_text(full_text, encoding='utf-8')

# === RUN ===
if __name__ == "__main__":
    crawler = UniversityCrawler()
    crawler.crawl()
