import os
import requests
import time
import urllib.robotparser
from urllib.parse import urljoin, urlparse
import tldextract
from bs4 import BeautifulSoup
import pdfplumber
from PIL import Image
import pytesseract
from io import BytesIO

# Configuration
SEED_URL = "https://fmuniversity.nic.in/index"
OUTPUT_FILE = "crawled_data.txt"
DELAY = 1  # seconds between requests
USER_AGENT = "Mozilla/5.0 (compatible; FMU-Crawler/1.0; +https://github.com/yourrepo)"
MAX_PAGES = 500
VISITED = set()
QUEUE = []
DOMAIN = "fmuniversity.nic.in"

# Robots.txt parser
rp = urllib.robotparser.RobotFileParser()
rp.set_url(urljoin(SEED_URL, "/robots.txt"))
try:
    rp.read()
except Exception as e:
    print(f"Could not read robots.txt: {e}")

def can_fetch(url):
    return rp.can_fetch(USER_AGENT, url)

def normalize_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip('/')

def is_same_domain(url):
    ext = tldextract.extract(url)
    return f"{ext.domain}.{ext.suffix}" == DOMAIN

def get_content_type(url):
    path = urlparse(url).path.lower()
    if path.endswith('.pdf'):
        return 'pdf'
    if path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
        return 'image'
    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        content_type = response.headers.get('content-type', '').lower()
        if 'application/pdf' in content_type:
            return 'pdf'
        if 'image/' in content_type:
            return 'image'
    except:
        pass
    return 'html'

def extract_html_text(url):
    try:
        resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=10)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        return soup.get_text(separator='\n', strip=True)
    except Exception as e:
        print(f"Error fetching HTML {url}: {e}")
        return None

def extract_pdf_text(url):
    try:
        resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            return None
        with pdfplumber.open(BytesIO(resp.content)) as pdf:
            return "\n".join([page.extract_text() or '' for page in pdf.pages])
    except Exception as e:
        print(f"Error processing PDF {url}: {e}")
        return None

def extract_image_text(url):
    try:
        resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=10)
        if resp.status_code != 200:
            return None
        img = Image.open(BytesIO(resp.content))
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        print(f"Error processing image {url}: {e}")
        return None

def save_to_file(url, content_type, text):
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
        f.write(f"\n=== URL: {url} ===\n")
        f.write(f"TYPE: {content_type.upper()}\n")
        f.write("CONTENT:\n")
        f.write(text if text else "[No extractable text]")
        f.write("\n" + "="*50 + "\n")

def crawl():
    QUEUE.append(SEED_URL)
    pages_crawled = 0

    while QUEUE and pages_crawled < MAX_PAGES:
        url = QUEUE.pop(0)
        norm_url = normalize_url(url)
        if norm_url in VISITED:
            continue
        if not is_same_domain(norm_url):
            continue
        if not can_fetch(norm_url):
            print(f"Skipping {norm_url} (disallowed by robots.txt)")
            continue

        VISITED.add(norm_url)
        print(f"Crawling: {norm_url}")

        ctype = get_content_type(norm_url)
        text = None

        if ctype == 'html':
            text = extract_html_text(norm_url)
            if text:
                save_to_file(norm_url, ctype, text)
                # Extract links
                try:
                    resp = requests.get(norm_url, headers={'User-Agent': USER_AGENT}, timeout=10)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        for link in soup.find_all('a', href=True):
                            href = urljoin(norm_url, link['href'])
                            if href.startswith(('http://', 'https://')) and is_same_domain(href):
                                norm_href = normalize_url(href)
                                if norm_href not in VISITED and norm_href not in QUEUE:
                                    QUEUE.append(norm_href)
                except Exception as e:
                    print(f"Error extracting links from {norm_url}: {e}")
        elif ctype == 'pdf':
            text = extract_pdf_text(norm_url)
            save_to_file(norm_url, ctype, text)
        elif ctype == 'image':
            text = extract_image_text(norm_url)
            save_to_file(norm_url, ctype, text)

        pages_crawled += 1
        time.sleep(DELAY)

    print(f"Crawling finished. Processed {pages_crawled} pages.")

if __name__ == "__main__":
    open(OUTPUT_FILE, 'w').close()
    crawl()
