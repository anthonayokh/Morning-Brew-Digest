"""
Personal News Digest
Automated daily news collection from multiple websites into a single email summary.
Author: anthonykh
Date: 02/02/2026
"""

import os
import sys
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import time
import logging
from typing import List, Dict, Tuple

# ========== SETUP LOGGING ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== CONFIGURATION CLASS ==========
class Config:
    """
    Configuration class for the news digest.
    Store sensitive data in environment variables for security.
    """
    
    # News sites to scrape (public - can be in code)
    NEWS_SITES = {
        "BBC": "https://www.bbc.com/news",
        "Reuters": "https://www.reuters.com/",
        "TechCrunch": "https://techcrunch.com/"
    }
    
    # Email configuration (set via environment variables)
    @staticmethod
    def get_email_config() -> Dict:
        """
        Get email configuration from environment variables.
        Returns error if variables are not set.
        """
        required_vars = ['EMAIL_SENDER', 'EMAIL_PASSWORD', 'EMAIL_RECEIVER']
        missing_vars = [var for var in required_vars if var not in os.environ]
        
        if missing_vars:
            logger.error(f"Missing environment variables: {missing_vars}")
            logger.error("Please set these variables before running:")
            logger.error("export EMAIL_SENDER='your_email@gmail.com'")
            logger.error("export EMAIL_PASSWORD='your_app_password'")
            logger.error("export EMAIL_RECEIVER='receiver@gmail.com'")
            sys.exit(1)
        
        return {
            "sender": os.environ['EMAIL_SENDER'],
            "password": os.environ['EMAIL_PASSWORD'],
            "receiver": os.environ['EMAIL_RECEIVER'],
            "smtp_server": "smtp.gmail.com",  # Change if using different provider
            "smtp_port": 587
        }

# ========== NEWS SCRAPER BASE CLASS ==========
class NewsScraper:
    """Base class for all news scrapers with common functionality"""
    
    def __init__(self, site_name: str, url: str):
        self.site_name = site_name
        self.url = url
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
    
    def fetch_page(self) -> Tuple[bool, BeautifulSoup]:
        """
        Fetch webpage and return BeautifulSoup object.
        Returns: (success: bool, soup: BeautifulSoup or None)
        """
        try:
            logger.info(f"Fetching {self.site_name}...")
            response = requests.get(
                self.url, 
                headers=self.headers, 
                timeout=10
            )
            response.raise_for_status()  # Raise exception for bad status codes
            
            # Respect robots.txt by adding delay
            time.sleep(2)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            return True, soup
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout while fetching {self.site_name}")
            return False, None
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error for {self.site_name}: {e}")
            return False, None
        except Exception as e:
            logger.error(f"Error fetching {self.site_name}: {e}")
            return False, None
    
    def scrape(self) -> List[str]:
        """
        Main scraping method to be overridden by child classes.
        Returns list of headlines.
        """
        raise NotImplementedError("Child classes must implement this method")

# ========== INDIVIDUAL SCRAPER CLASSES ==========
class BBCScraper(NewsScraper):
    """Scraper for BBC News website"""
    
    def scrape(self) -> List[str]:
        success, soup = self.fetch_page()
        if not success:
            return [f"Failed to fetch {self.site_name}"]
        
        headlines = []
        try:
            # BBC specific selectors
            # Look for headline elements (may need updating if BBC changes their HTML)
            for h3 in soup.find_all('h3', class_='gs-c-promo-heading__title')[:8]:
                text = h3.get_text(strip=True)
                if text and len(text) > 10:  # Filter out short text
                    headlines.append(text)
            
            # Alternative selector if primary fails
            if not headlines:
                for link in soup.find_all('a', {'data-testid': 'internal-link'})[:8]:
                    text = link.get_text(strip=True)
                    if text and len(text) > 15:
                        headlines.append(text)
            
            return headlines[:5]  # Return top 5 headlines
            
        except Exception as e:
            logger.error(f"Error parsing {self.site_name}: {e}")
            return [f"Error parsing {self.site_name}"]

class ReutersScraper(NewsScraper):
    """Scraper for Reuters website"""
    
    def scrape(self) -> List[str]:
        success, soup = self.fetch_page()
        if not success:
            return [f"Failed to fetch {self.site_name}"]
        
        headlines = []
        try:
            # Reuters specific selectors
            for element in soup.find_all(['h3', 'a'], class_='text__text__')[:10]:
                text = element.get_text(strip=True)
                if text and len(text) > 15:
                    headlines.append(text)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_headlines = []
            for h in headlines:
                if h not in seen:
                    seen.add(h)
                    unique_headlines.append(h)
            
            return unique_headlines[:5]
            
        except Exception as e:
            logger.error(f"Error parsing {self.site_name}: {e}")
            return [f"Error parsing {self.site_name}"]

class TechCrunchScraper(NewsScraper):
    """Scraper for TechCrunch website"""
    
    def scrape(self) -> List[str]:
        success, soup = self.fetch_page()
        if not success:
            return [f"Failed to fetch {self.site_name}"]
        
        headlines = []
        try:
            # TechCrunch specific selectors
            for h2 in soup.find_all('h2', class_='post-block__title')[:6]:
                text = h2.get_text(strip=True)
                if text:
                    headlines.append(text)
            
            return headlines[:5]
            
        except Exception as e:
            logger.error(f"Error parsing {self.site_name}: {e}")
            return [f"Error parsing {self.site_name}"]

# ========== EMAIL SENDER ==========
class EmailSender:
    """Handles sending emails via SMTP"""
    
    def __init__(self, config: Dict):
        self.config = config
    
    def send(self, subject: str, body: str) -> bool:
        """
        Send email with given subject and body.
        Returns: success (bool)
        """
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.config['sender']
            msg['To'] = self.config['receiver']
            msg['Subject'] = subject
            
            # Attach body
            msg.attach(MIMEText(body, 'plain'))
            
            # Connect to server and send
            logger.info("Connecting to SMTP server...")
            with smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port']) as server:
                server.starttls()
                server.login(self.config['sender'], self.config['password'])
                server.send_message(msg)
            
            logger.info("✓ Email sent successfully!")
            return True
            
        except smtplib.SMTPAuthenticationError:
            logger.error("✗ SMTP Authentication failed. Check your email and password.")
            logger.error("Note: For Gmail, you need to use an App Password, not your regular password.")
        except Exception as e:
            logger.error(f"✗ Error sending email: {e}")
        
        return False

# ========== MAIN NEWS DIGEST CLASS ==========
class NewsDigest:
    """Main class that orchestrates the news digest process"""
    
    def __init__(self):
        self.config = Config()
        self.email_config = Config.get_email_config()
        self.email_sender = EmailSender(self.email_config)
        
        # Map site names to scraper classes
        self.SCRAPERS = {
            "BBC": BBCScraper,
            "Reuters": ReutersScraper,
            "TechCrunch": TechCrunchScraper
        }
    
    def collect_news(self) -> Dict[str, List[str]]:
        """
        Collect news from all configured sites.
        Returns: Dictionary of {site_name: [headlines]}
        """
        logger.info("Starting news collection...")
        all_news = {}
        
        for site_name, site_url in self.config.NEWS_SITES.items():
            scraper_class = self.SCRAPERS.get(site_name)
            
            if scraper_class:
                scraper = scraper_class(site_name, site_url)
                headlines = scraper.scrape()
                all_news[site_name] = headlines
                logger.info(f"  ✓ {site_name}: Found {len(headlines)} headlines")
            else:
                logger.warning(f"  ✗ No scraper defined for {site_name}")
                all_news[site_name] = [f"No scraper available"]
        
        return all_news
    
    def format_digest(self, all_news: Dict[str, List[str]]) -> str:
        """
        Format collected news into a readable digest.
        Returns: Formatted string for email
        """
        current_time = datetime.now()
        
        # Build digest lines
        lines = []
        lines.append("=" * 50)
        lines.append("📰 PERSONAL NEWS DIGEST")
        lines.append(f"📅 {current_time.strftime('%A, %B %d, %Y')}")
        lines.append(f"🕒 Generated at: {current_time.strftime('%H:%M')}")
        lines.append("=" * 50)
        lines.append("")
        
        # Add news from each site
        for site_name, headlines in all_news.items():
            lines.append(f"【 {site_name.upper()} 】")
            lines.append(f"🔗 {self.config.NEWS_SITES[site_name]}")
            lines.append("")
            
            if headlines and "Error" not in headlines[0] and "Failed" not in headlines[0]:
                for i, headline in enumerate(headlines[:5], 1):
                    lines.append(f"{i}. {headline}")
            else:
                lines.append("  (Could not retrieve headlines)")
            
            lines.append("")
            lines.append("-" * 40)
            lines.append("")
        
        # Add summary
        lines.append("=" * 50)
        lines.append(f"📊 Summary: News from {len(all_news)} sources")
        lines.append("💡 Tip: Add more sources in Config.NEWS_SITES")
        lines.append("=" * 50)
        
        return "\n".join(lines)
    
    def run(self) -> bool:
        """
        Main method to run the entire news digest process.
        Returns: success (bool)
        """
        try:
            logger.info("=" * 60)
            logger.info("Starting Personal News Digest")
            logger.info("=" * 60)
            
            # Step 1: Collect news
            all_news = self.collect_news()
            
            # Step 2: Format digest
            digest = self.format_digest(all_news)
            
            # Step 3: Create email subject
            date_str = datetime.now().strftime('%Y-%m-%d')
            subject = f"📰 Your Personal News Digest - {date_str}"
            
            # Step 4: Send email
            success = self.email_sender.send(subject, digest)
            
            if success:
                logger.info("=" * 60)
                logger.info("News digest completed successfully!")
                logger.info("=" * 60)
            
            return success
            
        except Exception as e:
            logger.error(f"Unexpected error in main process: {e}")
            return False

# ========== MAIN EXECUTION ==========
if __name__ == "__main__":
   
    
    # Create and run news digest
    digest = NewsDigest()
    success = digest.run()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
