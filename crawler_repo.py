import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import random
import csv
import json
import os
import shutil
from collections import deque
import re
from urllib.robotparser import RobotFileParser
import logging

# Additional libraries for PDF and image processing
import pdfplumber
import io
from PIL import Image
import pytesseract
import base64
import mimetypes

class RepositoryWebCrawler:
 def __init__(self, base_url, repo_path='.', branch='main', delay=1, max_depth=3, max_pages=50, 
 handle_pdfs=True, handle_images=True, max_file_size_mb=5, file_naming='safe'):
 """
 Initialize the web crawler with repository file saving capabilities
 
 Args:
 base_url (str): Starting URL for crawling
 repo_path (str): Local repository path for saving files
 branch (str): Git branch to commit to
 delay (float): Delay between requests in seconds
 max_depth (int): Maximum recursion depth
 max_pages (int): Maximum number of pages to crawl
 handle_pdfs (bool): Whether to process PDF files
 handle_images (bool): Whether to process images with OCR
 max_file_size_mb (int): Maximum file size to process in MB
 file_naming (str): File naming strategy ('safe', 'timestamp', 'slug')
 """
 self.base_url = base_url
 self.domain = urlparse(base_url).netloc
 self.delay = delay
 self.max_depth = max_depth
 self.max_pages = max_pages
 self.handle_pdfs = handle_pdfs
 self.handle_images = handle_images
 self.max_file_size = max_file_size_mb * 1024 * 1024 # Convert to bytes
 self.repo_path = repo_path
 self.branch = branch
 self.file_naming = file_naming
 
 # Data structures
 self.visited_urls = set()
 self.url_queue = deque()
 self.crawled_data = []
 self.processed_files = []
 
 # Initialize logging
 logging.basicConfig(level=logging.INFO)
 self.logger = logging.getLogger(__name__)
 
 # Initialize robot parser
 self.robot_parser = RobotFileParser()
 self.robot_parser.set_url(urljoin(base_url, '/robots.txt'))
 
 # User agent rotation
 self.user_agents = [
 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
 ]
 
 def can_fetch(self, url):
 """Check if we can fetch the URL according to robots.txt"""
 try:
 self.robot_parser.set_url(urljoin(self.base_url, '/robots.txt'))
 self.robot_parser.read()
 return self.robot_parser.can_fetch('*', url)
 except:
 return True
 
 def get_random_user_agent(self):
 """Get a random user agent"""
 return random.choice(self.user_agents)
 
 def is_valid_url(self, url):
 """Check if URL is valid and within the same domain"""
 try:
 parsed = urlparse(url)
 return parsed.netloc == self.domain and parsed.scheme in ('http', 'https')
 except:
 return False
 
 def normalize_url(self, url):
 """Normalize URL by removing fragments and sorting query parameters"""
 parsed = urlparse(url)
 normalized = parsed._replace(fragment='', params='')
 return normalized.geturl()
 
 def clean_text(self, text):
 """Clean and normalize text content"""
 if not text:
 return ""
 return ' '.join(text.split())
 
 def get_file_extension(self, url):
 """Extract file extension from URL"""
 return urlparse(url).path.split('.')[-1].lower()
 
 def is_supported_file(self, url):
 """Check if file type is supported for processing"""
 if not self.handle_pdfs and self.get_file_extension(url) == 'pdf':
 return False
 if not self.handle_images and self.get_file_extension(url) in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff']:
 return False
 return True
 
 def get_file_size(self, response):
 """Get file size in bytes"""
 return len(response.content)
 
 def create_filename(self, url, content, content_type):
 """Create filename based on URL and content"""
 domain = urlparse(url).netloc
 path_parts = urlparse(url).path.strip('/').split('/')
 filename_base = path_parts[-1] if path_parts[-1] else domain
 
 # Remove extension for content files
 if filename_base.endswith('.pdf') or filename_base.endswith('.jpg') or filename_base.endswith('.png'):
 filename_base = filename_base[:-4]
 
 if self.file_naming == 'safe':
 # Safe naming: replace special characters
 safe_name = re.sub(r'[^\w\-_.]', '_', filename_base)
 safe_name = re.sub(r'_+', '_', safe_name)
 return f"{domain}_{safe_name}"
 
 elif self.file_naming == 'slug':
 # Slug naming: convert to lowercase with dashes
 slug_name = filename_base.lower()
 slug_name = re.sub(r'[^\w\-_.]', '-', slug_name)
 slug_name = re.sub(r'-+', '-', slug_name)
 return f"{domain}-{slug_name}"
 
 else: # timestamp
 # Timestamp-based naming
 timestamp = int(time.time())
 safe_name = re.sub(r'[^\w\-_.]', '_', filename_base)
 return f"{domain}_{timestamp}_{safe_name}"
 
 def save_content_to_repo(self, url, content, content_type, metadata=None):
 """Save extracted content to repository with structured organization"""
 try:
 # Create directory structure
 domain_folder = urlparse(url).netloc.replace('.', '_')
 date_str = time.strftime('%Y-%m-%d')
 
 if content_type == 'application/pdf':
 category = 'pdfs'
 elif content_type.startswith('image/'):
 category = 'images'
 else:
 category = 'webpages'
 
 # Create directories
 base_dir = os.path.join(self.repo_path, 'crawled_content')
 category_dir = os.path.join(base_dir, category, domain_folder, date_str)
 os.makedirs(category_dir, exist_ok=True)
 
 # Generate filename
 filename = self.create_filename(url, content, content_type)
 if content_type == 'application/pdf' or content_type.startswith('image/'):
 filename += f"._{content_type.split('/')[1]}"
 else:
 filename += '.html'
 
 # Check for filename conflicts and add counter if needed
 counter = 1
 original_filename = filename
 while os.path.exists(os.path.join(category_dir, filename)):
 name, ext = os.path.splitext(original_filename)
 filename = f"{name}_{counter}{ext}"
 counter += 1
 
 file_path = os.path.join(category_dir, filename)
 
 # Save content
 if content_type == 'application/pdf':
 # Process PDF content
 pdf_text = self.extract_text_from_pdf(url, content)
 
 # Save extracted text
 with open(file_path, 'w', encoding='utf-8') as f:
 f.write(f"URL: {url}\n")
 f.write(f"Title: {metadata.get('title', 'N/A')}\n")
 f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
 f.write(f"Content Type: {content_type}\n")
 f.write("-" * 50 + "\n\n")
 f.write(pdf_text)
 
 # Also save metadata
 metadata_path = file_path.replace('.txt', '_metadata.json')
 with open(metadata_path, 'w', encoding='utf-8') as f:
 metadata_info = {
 'url': url,
 'title': metadata.get('title', ''),
 'crawl_depth': metadata.get('crawl_depth', 0),
 'status_code': metadata.get('status_code', 200),
 'content_type': content_type,
 'domain': self.domain,
 'extracted_on': time.strftime('%Y-%m-%d %H:%M:%S'),
 'file_size_kb': len(content) / 1024
 }
 json.dump(metadata_info, f, indent=2, ensure_ascii=False)
 
 elif content_type.startswith('image/'):
 # Process image content
 image_text = self.extract_text_from_image(url, content)
 
 # Save extracted text
 with open(file_path, 'w', encoding='utf-8') as f:
 f.write(f"URL: {url}\n")
 f.write(f"Title: {metadata.get('title', 'N/A')}\n")
 f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
 f.write(f"Content Type: {content_type}\n")
 f.write("-" * 50 + "\n\n")
 f.write(image_text)
 
 # Also save metadata
 metadata_path = file_path.replace('.txt', '_metadata.json')
 with open(metadata_path, 'w', encoding='utf-8') as f:
 metadata_info = {
 'url': url,
 'title': metadata.get('title', ''),
 'crawl_depth': metadata.get('crawl_depth', 0),
 'status_code': metadata.get('status_code', 200),
 'content_type': content_type,
 'domain': self.domain,
 'extracted_on': time.strftime('%Y-%m-%d %H:%M:%S'),
 'file_size_kb': len(content) / 1024,
 'image_processed': True
 }
 json.dump(metadata_info, f, indent=2, ensure_ascii=False)
 
 else:
 # Save HTML content
 with open(file_path, 'w', encoding='utf-8') as f:
 f.write(f"URL: {url}\n")
 f.write(f"Title: {metadata.get('title', 'N/A')}\n")
 f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
 f.write(f"Content Type: {content_type}\n")
 f.write(f"Crawl Depth: {metadata.get('crawl_depth', 0)}\n")
 f.write("-" * 50 + "\n\n")
 f.write(content.decode('utf-8', errors='ignore'))
 
 # Also save metadata
 metadata_path = file_path.replace('.html', '_metadata.json')
 with open(metadata_path, 'w', encoding='utf-8') as f:
 metadata_info = {
 'url': url,
 'title': metadata.get('title', ''),
 'crawl_depth': metadata.get('crawl_depth', 0),
 'status_code': metadata.get('status_code', 200),
 'content_type': content_type,
 'domain': self.domain,
 'extracted_on': time.strftime('%Y-%m-%d %H:%M:%S')
 }
 json.dump(metadata_info, f, indent=2, ensure_ascii=False)
 
 self.processed_files.append({
 'url': url,
 'file_path': file_path,
 'type': content_type,
 'saved': True
 })
 
 self.logger.info(f"Saved content to: {file_path}")
 return file_path
 
 except Exception as e:
 self.logger.error(f"Error saving content from {url}: {str(e)}")
 return None
 
 def extract_text_from_pdf(self, url, content):
 """Extract text from PDF content"""
 try:
 with io.BytesIO(content) as pdf_file:
 with pdfplumber.open(pdf_file) as pdf:
 full_text = ""
 for page in pdf.pages:
 full_text += page.extract_text() + "\n"
 return self.clean_text(full_text)
 except Exception as e:
 self.logger.error(f"Error extracting PDF text from {url}: {str(e)}")
 return f"Error: {str(e)}"
 
 def extract_text_from_image(self, url, content):
 """Extract text from image using OCR"""
 try:
 # Convert content to PIL Image
 image_data = io.BytesIO(content)
 image = Image.open(image_data)
 
 # Resize image for better OCR (limit max dimensions)
 max_width, max_height = 2000, 2000
 if image.width > max_width or image.height > max_height:
 image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
 
 # Convert to grayscale for better OCR
 if image.mode != 'L':
 image = image.convert('L')
 
 # Extract text using OCR
 extracted_text = pytesseract.image_to_string(image)
 return self.clean_text(extracted_text)
 except Exception as e:
 self.logger.error(f"Error extracting text from image {url}: {str(e)}")
 return f"Error: {str(e)}"
 
 def extract_page_data(self, url, response, content_type='text/html'):
 """Extract relevant data from the page"""
 data = {
 'url': url,
 'title': '',
 'headings': [],
 'paragraphs': [],
 'links': [],
 'images': [],
 'pdfs': [],
 'extracted_texts': [],
 'crawl_depth': 0,
 'status_code': response.status_code,
 'content_type': content_type
 }
 
 if content_type == 'text/html':
 soup = BeautifulSoup(response.content, 'html.parser')
 
 # Extract title
 title_tag = soup.find('title')
 if title_tag:
 data['title'] = self.clean_text(title_tag.get_text())
 
 # Extract meta description
 meta_desc = soup.find('meta', attrs={'name': 'description'})
 if meta_desc:
 data['meta_description'] = self.clean_text(meta_desc.get('content', ''))
 
 # Extract headings
 for i in range(1, 7):
 headings = soup.find_all(f'h{i}')
 for heading in headings:
 data['headings'].append({
 'level': i,
 'text': self.clean_text(heading.get_text())
 })
 
 # Extract paragraphs
 paragraphs = soup.find_all('p')
 for p in paragraphs:
 text = self.clean_text(p.get_text())
 if text:
 data['paragraphs'].append(text)
 
 # Extract links
 links = self.extract_links(soup, url)
 data['links'] = links[:10] # Limit to first 10 links
 
 # Extract images
 images = []
 for img in soup.find_all('img'):
 src = img.get('src')
 if src:
 images.append(urljoin(url, src))
 data['images'] = images[:5] # Limit to first 5 images
 
 # Extract PDFs
 if self.handle_pdfs:
 pdfs = []
 for link in soup.find_all('a', href=True):
 if link['href'].endswith('.pdf'):
 pdf_url = urljoin(url, link['href'])
 pdfs.append(pdf_url)
 data['pdfs'] = pdfs[:3] # Limit to first 3 PDFs
 
 else:
 data['pdfs'] = []
 
 else:
 data['pdfs'] = []
 data['images'] = []
 
 elif content_type == 'application/pdf':
 # Handle PDF content
 pdf_text = self.extract_text_from_pdf(url, response.content)
 data['extracted_texts'] = [pdf_text]
 data['pdfs'] = [url]
 
 elif content_type.startswith('image/'):
 # Handle image content
 image_text = self.extract_text_from_image(url, response.content)
 data['extracted_texts'] = [image_text]
 
 else:
 # Handle other content types
 data['extracted_texts'] = [f"Content type: {content_type}"]
 
 return data
 
 def extract_links(self, soup, current_url):
 """Extract all valid links from the page"""
 links = []
 for link in soup.find_links():
 href = link.get('href')
 if href and not href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
 full_url = urljoin(current_url, href)
 normalized_url = self.normalize_url(full_url)
 links.append(normalized_url)
 return links
 
 def crawl_page(self, url, depth=0):
 """Crawl a single page with enhanced file handling"""
 if depth > self.max_depth:
 return None
 
 if url in self.visited_urls:
 return None
 
 if len(self.visited_urls) >= self.max_pages:
 return None
 
 if not self.can_fetch(url):
 self.logger.warning(f"Cannot fetch {url} (robots.txt restriction)")
 return None
 
 self.visited_urls.add(url)
 self.logger.info(f"Crawling: {url} (Depth: {depth}, Visited: {len(self.visited_urls)})")
 
 try:
 headers = {'User-Agent': self.get_random_user_agent()}
 response = requests.get(url, headers=headers, timeout=30)
 
 # Check file size limit
 if self.get_file_size(response) > self.max_file_size:
 self.logger.warning(f"File too large: {url} ({self.get_file_size(response)/1024/1024:.2f}MB)")
 return None
 
 # Check content type
 content_type = response.headers.get('content-type', '')
 content = response.content
 
 # Extract data based on content type
 if content_type.startswith('text/html'):
 page_data = self.extract_page_data(url, response, content_type)
 
 # Save HTML page to repository
 metadata = {
 'title': page_data.get('title', ''),
 'crawl_depth': depth,
 'status_code': response.status_code
 }
 self.save_content_to_repo(url, content, content_type, metadata)
 
 # Queue additional file types found on the page
 if self.handle_pdfs and 'pdfs' in page_data and page_data['pdfs']:
 for pdf_url in page_data['pdfs']:
 if pdf_url not in self.visited_urls and self.is_valid_url(pdf_url):
 self.url_queue.append((pdf_url, depth + 1))
 
 elif content_type == 'application/pdf':
 # Directly process PDF
 page_data = self.extract_page_data(url, response, content_type)
 metadata = {
 'title': page_data.get('title', ''),
 'crawl_depth': depth,
 'status_code': response.status_code
 }
 self.save_content_to_repo(url, response.content, content_type, metadata)
 
 elif content_type.startswith('image/') and self.handle_images:
 # Directly process image
 page_data = self.extract_page_data(url, response, content_type)
 metadata = {
 'title': page_data.get('title', ''),
 'crawl_depth': depth,
 'status_code': response.status_code
 }
 self.save_content_to_repo(url, response.content, content_type, metadata)
 
 else:
 # Unsupported content type
 self.logger.info(f"Skipping unsupported content type: {content_type}")
 return None
 
 # Add crawling metadata
 page_data['crawl_depth'] = depth
 
 # Add extracted content to processed files list
 if page_data.get('extracted_texts'):
 self.processed_files.append({
 'url': url,
 'type': content_type,
 'extracted_content': page_data['extracted_texts']
 })
 
 self.crawled_data.append(page_data)
 
 # Extract and queue new links for recursive crawling
 if content_type.startswith('text/html'):
 links = self.extract_links(BeautifulSoup(response.content, 'html.parser'), url)
 for link in links:
 if link not in self.visited_urls and self.is_valid_url(link):
 self.url_queue.append((link, depth + 1))
 
 # Respectful delay between requests
 delay = self.delay + random.uniform(0, 1)
 time.sleep(delay)
 
 return page_data
 else:
 self.logger.warning(f"HTTP {response.status_code} for {url}")
 return None
 
 except Exception as e:
 self.logger.error(f"Error crawling {url}: {str(e)}")
 return None
 
 def start_crawling(self):
 """Start the recursive crawling process"""
 self.url_queue.append((self.base_url, 0))
 crawled_count = 0
 pdf_count = 0
 image_count = 0
 
 while self.url_queue and crawled_count < self.max_pages:
 url, depth = self.url_queue.popleft()
 result = self.crawl_page(url, depth)
 if result:
 crawled_count += 1
 
 # Count file types
 if result.get('pdfs'):
 pdf_count += len(result['pdfs'])
 if result.get('extracted_texts'):
 for text in result['extracted_texts']:
 if 'Error:' not in text:
 image_count += 1
 
 self.logger.info(f"Progress: {crawled_count}/{self.max_pages} pages, "
 f"{len(self.processed_files)} files processed, "
 f"{pdf_count} PDFs found, {image_count} images processed")
 
 return self.crawled_data
 
 def save_to_csv(self, filename='crawled_data.csv'):
 """Save crawled data to CSV file"""
 if not self.crawled_data:
 self.logger.warning("No data to save")
 return
 
 with open(filename, 'w', newline='', encoding='utf-8') as file:
 fieldnames = ['url', 'title', 'headings', 'paragraphs', 'links', 'images', 
 'pdfs', 'extracted_texts', 'crawl_depth', 'status_code', 'content_type']
 writer = csv.DictWriter(file, fieldnames=fieldnames)
 writer.writeheader()
 
 for data in self.crawled_data:
 row = {}
 for key in fieldnames:
 if key in data:
 value = data[key]
 if isinstance(value, list):
 row[key] = '; '.join(map(str, value))
 elif isinstance(value, dict):
 row[key] = json.dumps(value)
 else:
 row[key] = value
 writer.writerow(row)
 
 self.logger.info(f"Data saved to {filename}")
 
 def save_to_json(self, filename='crawled_data.json'):
 """Save crawled data to JSON file"""
 if not self.crawled_data:
 self.logger.warning("No data to save")
 return
 
 output_data = {
 'crawl_metadata': {
 'base_url': self.base_url,
 'domain': self.domain,
 'total_crawled': len(self.crawled_data),
 'unique_urls': len(self.visited_urls),
 'max_depth_reached': max([d['crawl_depth'] for d in self.crawled_data]) if self.crawled_data else 0
 },
 'processed_files': self.processed_files,
 'crawled_data': self.crawled_data
 }
 
 with open(filename, 'w', encoding='utf-8') as file:
 json.dump(output_data, file, indent=2, ensure_ascii=False)
 
 self.logger.info(f"Data saved to {filename}")
 
 def get_crawl_statistics(self):
 """Get crawling statistics"""
 return {
 'total_crawled': len(self.crawled_data),
 'unique_urls': len(self.visited_urls),
 'domain': self.domain,
 'max_depth_reached': max([d['crawl_depth'] for d in self.crawled_data]) if self.crawled_data else 0,
 'pages_with_images': sum(1 for d in self.crawled_data if d['images']),
 'pages_with_pdfs': sum(1 for d in self.crawled_data if d['pdfs']),
 'extracted_texts_count': len(self.processed_files),
 'pdfs_found': sum(1 for d in self.crawled_data if d['pdfs']),
 'images_processed': sum(1 for d in self.crawled_data if d.get('extracted_texts'))
 }
 
 def create_file_index(self, filename='file_index.json'):
 """Create an index of all saved files"""
 index = {
 'crawl_info': {
 'base_url': self.base_url,
 'crawl_date': time.strftime('%Y-%m-%d %H:%M:%S'),
 'total_files': len(self.processed_files)
 },
 'files': []
 }
 
 for file_data in self.processed_files:
 file_info = {
 'url': file_data['url'],
 'file_path': file_data['file_path'],
 'type': file_data['type'],
 'extracted_on': time.strftime('%Y-%m-%d %H:%M:%S')
 }
 index['files'].append(file_info)
 
 with open(filename, 'w', encoding='utf-8') as f:
 json.dump(index, f, indent=2, ensure_ascii=False)
 
 self.logger.info(f"File index saved to {filename}")
 
 def initialize_repo_structure(self):
 """Initialize the repository structure for crawled content"""
 base_dir = os.path.join(self.repo_path, 'crawled_content')
 directories = [
 'webpages',
 'pdfs',
 'images',
 'pdfs/processed',
 'images/processed'
 ]
 
 for directory in directories:
 full_path = os.path.join(base_dir, directory)
 os.makedirs(full_path, exist_ok=True)
 
 # Create README for the crawled content
 readme_path = os.path.join(base_dir, 'README.md')
 if not os.path.exists(readme_path):
 with open(readme_path, 'w', encoding='utf-8') as f:
 f.write("# Crawled Content\n\n")
 f.write(f"This directory contains content extracted from crawling {self.base_url}\n\n")
 f.write("## Directory Structure\n\n")
 f.write("- **webpages/**: HTML pages saved as text files\n")
 f.write("- **pdfs/**: PDF files with extracted text\n")
 f.write("- **images/**: Images with OCR-extracted text\n")
 f.write("- Each file has a corresponding _metadata.json file with extraction details\n\n")
 f.write("## File Naming\n\n")
 f.write("Files are named using the pattern: `{domain}_{safe_name}.{extension}`\n\n")
 f.write("## Generated Files\n\n")
 f.write("- `file_index.json`: Index of all extracted files\n")
 f.write("- `crawl_statistics.json`: Crawl statistics and metadata\n")
 
 # Also save crawl statistics
 stats = self.get_crawl_statistics()
 stats_path = os.path.join(base_dir, 'crawl_statistics.json')
 with open(stats_path, 'w', encoding='utf-8') as f:
 json.dump(stats, f, indent=2, ensure_ascii=False)

# Usage Example
if __name__ == '__main__':
 import sys
 
 base_url = sys.argv if len(sys.argv) > 1 else 'https://fmuniversity.nic.in/index'
 max_depth = int(sys.argv) if len(sys.argv) > 2 else 2
 max_pages = int(sys.argv) if len(sys.argv) > 3 else 20
 delay = float(sys.argv) if len(sys.argv) > 4 else 1.5
 handle_pdfs = sys.argv.lower() == 'true' if len(sys.argv) > 5 and sys.argv.lower() == 'true' else True
 handle_images = sys.argv.lower() == 'true' if len(sys.argv) > 6 and sys.argv.lower() == 'true' else True
 output_format = sys.argv if len(sys.argv) > 7 else 'json'
 repo_path = sys.argv if len(sys.argv) > 8 else '.'
 file_naming = sys.argv if len(sys.argv) > 9 else 'safe'
 
 crawler = RepositoryWebCrawler(
 base_url=base_url,
 delay=delay,
 max_depth=max_depth,
 max_pages=max_pages,
 handle_pdfs=handle_pdfs,
 handle_images=handle_images,
 file_naming=file_naming,
 repo_path=repo_path
 )
 
 # Initialize repository structure
 crawler.initialize_repo_structure()
 
 # Start crawling
 crawled_data = crawler.start_crawling()
 
 # Create file index
 crawler.create_file_index()
 
 stats = crawler.get_crawl_statistics()
 
 # Save results
 with open('stats.json', 'w') as f:
 json.dump(stats, f, indent=2)
 
 if output_format.lower() == 'json':
 crawler.save_to_json('crawled_data.json')
 else:
 crawler.save_to_csv('crawled_data.csv')
 
 print(f"Crawl completed! Statistics:")
 for key, value in stats.items():
 print(f" {key}: {value}")
 
 print(f"\nContent saved to repository in 'crawled_content/' directory")
