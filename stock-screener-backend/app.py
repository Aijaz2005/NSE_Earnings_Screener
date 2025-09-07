from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import os
from dotenv import load_dotenv
import logging
import time
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import yfinance as yf
from datetime import datetime, timedelta
import traceback
import threading
import io

# Add Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST"]}})  # Allow all origins and methods

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize User-Agent rotator
ua = UserAgent()

# Setup requests session with retries for 429
session = requests.Session()
retries = Retry(total=3, backoff_factor=2, status_forcelist=[429])
session.mount('https://', HTTPAdapter(max_retries=retries))

# Global variable for NSE mapping (initialized lazily)
nse_mapping = {}

def load_nse_mapping():
    """Load NSE mapping in a separate thread to avoid blocking server startup."""
    global nse_mapping
    url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    try:
        logger.debug("Fetching NSE EQUITY_L.csv in background thread")
        response = session.get(url, headers={'User-Agent': ua.random}, timeout=10)
        if response.status_code != 200:
            raise ValueError(f"Failed to fetch EQUITY_L.csv: {response.status_code}")
        # Use StringIO to handle CSV content as a file-like object
        nse_df = pd.read_csv(io.StringIO(response.text), encoding='utf-8')
        
        # Print column names to debug
        logger.debug(f"NSE CSV columns: {list(nse_df.columns)}")
        
        # Use the correct column names
        mapping = dict(zip(nse_df['NAME OF COMPANY'].str.lower(), nse_df['SYMBOL']))
        nse_mapping.update(mapping)
        logger.info(f"Loaded {len(nse_mapping)} NSE symbols from EQUITY_L.csv")
        
        # Debug: Print a few sample mappings
        sample_items = list(mapping.items())[:5]
        logger.debug(f"Sample mappings: {sample_items}")
        
    except Exception as e:
        logger.error(f"Error loading NSE mapping: {str(e)} with traceback: {traceback.format_exc()}")

# Start NSE mapping load in a background thread
threading.Thread(target=load_nse_mapping, daemon=True).start()

def get_earnings(symbol):
    """
    Enhanced scraping logic with URL fallback and rate limit handling
    """
    base_url = f"https://www.screener.in/company/{symbol.upper()}"
    urls = [f"{base_url}/consolidated/#quarters", f"{base_url}/#quarters"]

    for url in urls:
        headers = {'User-Agent': ua.random}
        
        try:
            logger.debug(f"{symbol}: Fetching URL: {url} with User-Agent: {headers['User-Agent']}")
            response = session.get(url, headers=headers, timeout=10)
            logger.debug(f"{symbol}: HTTP status: {response.status_code}")
            if response.status_code != 200:
                raise ValueError(f"Failed to fetch page for {symbol}: {response.status_code}")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            logger.debug(f"{symbol}: HTML length: {len(response.text)}")
           
            # Extract Market Cap with improved regex patterns
            market_cap = None
            top_ratios = soup.find('ul', id='top-ratios')
            if top_ratios:
                logger.debug(f"{symbol}: Found top-ratios ul")
                for li in top_ratios.find_all('li'):
                    text = li.text.strip().replace('\xa0', ' ')
                    logger.debug(f"{symbol}: Checking li: {text}")
                    if 'Market Cap' in text:
                        # Multiple regex patterns to handle different formats
                        patterns = [
                            r'₹\s*([\d,]+)\s*Cr\.?',  # ₹18,60,714 Cr.
                            r'Rs\.\s*([\d,]+)\s*Cr\.?',  # Rs. 18,60,714 Cr.
                            r'([\d,]+)\s*Cr\.?',  # 18,60,714 Cr.
                            r'₹\s*([\d,]+)',  # ₹18,60,714
                            r'Rs\.\s*([\d,]+)',  # Rs. 18,60,714
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, text)
                            if match:
                                market_cap = match.group(1).replace(',', '')
                                logger.debug(f"{symbol}: Market cap matched with pattern '{pattern}': {market_cap}")
                                break
                        
                        if market_cap:
                            break
                        else:
                            # If no pattern matches, log the full text for debugging
                            logger.warning(f"{symbol}: Market cap text found but no pattern matched: '{text}'")
            else:
                logger.warning(f"{symbol}: No top-ratios ul found")
                
            logger.info(f"{symbol}: Market Cap = {market_cap}")
           
            # Extract Quarterly Table
            section = soup.find('section', id='quarters')
            if not section:
                logger.warning(f"{symbol}: Quarters section not found, trying alternative")
                section = soup.find('section', class_='card card-large')
                if not section:
                    continue
            
            table = section.find('table')
            if not table:
                logger.warning(f"{symbol}: Data table not found")
                continue
            
            rows = table.find_all('tr')
            data = []
            for row in rows:
                cols = row.find_all(['td', 'th'])
                cols_text = [col.text.strip() for col in cols if col.text.strip()]
                if cols_text:
                    data.append(cols_text)
                else:
                    logger.debug(f"{symbol}: Skipping empty row: {row}")
            
            logger.debug(f"{symbol}: Parsed {len(data)} rows: {[row[0] for row in data]}")
            if len(data) < 1:
                continue
            
            quarters = data[0][1:] if len(data[0]) > 1 else []
            logger.info(f"{symbol}: Found {len(quarters)} quarters: {quarters}")
            if len(quarters) < 1 and url != urls[-1]:
                continue
            
            metrics = []
            values = []
            
            for row in data[1:]:
                metric = row[0].rstrip(' +')
                if metric == 'Raw PDF' or not metric:
                    continue
                vals = []
                for v in row[1:]:
                    if v == '':
                        vals.append(None)
                    elif '%' in v:
                        try:
                            vals.append(float(v.rstrip('%')))
                        except ValueError:
                            vals.append(None)
                            logger.debug(f"{symbol}: Failed to parse percentage: {v}")
                    else:
                        try:
                            vals.append(float(v.replace(',', '')))
                        except ValueError:
                            vals.append(None)
                            logger.debug(f"{symbol}: Failed to parse numeric: {v}")
                metrics.append(metric)
                values.append(vals)
            
            logger.debug(f"{symbol}: Parsed {len(metrics)} metrics: {metrics}")
            
            # Adjust sales index to handle variations
            sales_idx = next((i for i, m in enumerate(metrics) if 'Sales' in m), -1)
            if sales_idx == -1:
                logger.warning(f"{symbol}: 'Sales' metric not found in {metrics}")
            op_profit_idx = next((i for i, m in enumerate(metrics) if m == 'Operating Profit'), -1)
            opm_idx = next((i for i, m in enumerate(metrics) if m == 'OPM %'), -1)
            eps_idx = next((i for i, m in enumerate(metrics) if m == 'EPS in Rs'), -1)
           
            sales = values[sales_idx] if sales_idx != -1 else [None] * len(quarters)
            op_profit = values[op_profit_idx] if op_profit_idx != -1 else [None] * len(quarters)
            opm = values[opm_idx] if opm_idx != -1 else [None] * len(quarters)
            eps = values[eps_idx] if eps_idx != -1 else [None] * len(quarters)
           
            sales = [int(x) if x is not None else None for x in sales]
            op_profit = [int(x) if x is not None else None for x in op_profit]
            opm = [int(x) if x is not None else None for x in opm]
           
            def calc_pct(current, prev):
                if prev == 0 or prev is None or current is None:
                    return 'N/A'
                return int(round((current - prev) / abs(prev) * 100, 0))
            
            sales_qoq = ['N/A'] + [calc_pct(sales[i], sales[i-1]) for i in range(1, len(sales))] if sales and any(x is not None for x in sales) else ['N/A'] * len(quarters)
            sales_yoy = ['N/A'] * min(4, len(sales)) + [calc_pct(sales[i], sales[i-4]) for i in range(4, len(sales))] if sales and any(x is not None for x in sales) else ['N/A'] * len(quarters)
           
            num_qtrs = min(len(quarters), 8)
            logger.info(f"{symbol}: Using {num_qtrs} quarters")
            
            quarters_latest_first = quarters[-num_qtrs:][::-1] if quarters else []
            sales_latest_first = sales[-num_qtrs:][::-1] if quarters else []
            op_profit_latest_first = op_profit[-num_qtrs:][::-1] if quarters else []
            opm_latest_first = opm[-num_qtrs:][::-1] if quarters else []
            eps_latest_first = eps[-num_qtrs:][::-1] if quarters else []
            sales_qoq_latest_first = sales_qoq[-num_qtrs:][::-1] if quarters else []
            sales_yoy_latest_first = sales_yoy[-num_qtrs:][::-1] if quarters else []
           
            result = {
                'symbol': symbol.upper(),
                'marketCap': market_cap,
                'quarters': quarters_latest_first,
                'metrics': {
                    'Sales': sales_latest_first,
                    'Operating Profit': op_profit_latest_first,
                    'OPM %': opm_latest_first,
                    'EPS in Rs': eps_latest_first,
                    'Sales YoY %': sales_yoy_latest_first,
                    'Sales QoQ %': sales_qoq_latest_first
                }
            }
            
            logger.info(f"{symbol}: Successfully fetched {len(quarters_latest_first)} quarters")
            return result
            
        except Exception as e:
            logger.error(f"Error scraping {symbol}: {str(e)} with traceback: {traceback.format_exc()}")
            if url == urls[-1]:
                return {'symbol': symbol.upper(), 'marketCap': market_cap, 'quarters': [], 'metrics': {}, 'error': str(e)}
            else:
                continue

@app.route('/api/stock/<symbol>', methods=['GET'])
def get_stock_data(symbol):
    logger.debug(f"Received GET request for /api/stock/{symbol}")
    try:
        result = get_earnings(symbol)
        if 'error' in result:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 400
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        logger.error(f"Exception in /api/stock/{symbol}: {str(e)} with traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stocks', methods=['POST'])
def get_multiple_stocks():
    logger.debug(f"Received POST request for /api/stocks with data: {request.get_json()}")
    data = request.get_json()
    symbols = data.get('symbols', [])
    
    if not symbols:
        return jsonify({
            'success': False,
            'error': 'No symbols provided'
        }), 400
    
    results = {}
    errors = {}
    
    for symbol in symbols:
        try:
            result = get_earnings(symbol)
            if 'error' in result:
                errors[symbol] = result['error']
            else:
                results[symbol] = result
            time.sleep(5)
        except Exception as e:
            errors[symbol] = str(e)
            logger.error(f"Error processing {symbol}: {str(e)} with traceback: {traceback.format_exc()}")
    
    return jsonify({
        'success': True,
        'results': results,
        'errors': errors
    })

def find_nse_symbol(company_name):
    """Helper function to find NSE symbol for a company"""
    if not nse_mapping:
        logger.warning("NSE mapping not loaded yet")
        return None
    
    company_lower = company_name.lower()
    
    # Try exact match first
    if company_lower in nse_mapping:
        return nse_mapping[company_lower]
    
    # Try partial matches for known stock name variations
    # Common mappings for stocks we know are listed
    known_mappings = {
        'hdil': 'HDIL',
        'india cements': 'INDIACEM',
        'ultratech cement': 'ULTRACEMCO',
        'coforge': 'COFORGE',
        'regaal': None,  # Not in NSE
        'vikram solar': None,  # Not sure if listed
        'sugar': None  # Generic term
    }
    
    if company_lower in known_mappings:
        return known_mappings[company_lower]
    
    # Try fuzzy matching on company name
    for nse_company, nse_symbol in nse_mapping.items():
        # Check if any significant word from BSE company name is in NSE company name
        company_words = [word for word in company_lower.split() if len(word) > 3]
        nse_words = [word for word in nse_company.split() if len(word) > 3]
        
        # If at least 60% of significant words match
        if company_words:
            matches = sum(1 for word in company_words if any(word in nse_word or nse_word in word for nse_word in nse_words))
            if matches / len(company_words) >= 0.6:
                logger.debug(f"Fuzzy matched '{company_name}' -> '{nse_company}' -> {nse_symbol}")
                return nse_symbol
    
    return None

@app.route('/api/upcoming_results', methods=['GET'])
def get_upcoming_results():
    logger.debug("Received GET request for /api/upcoming_results")
    
    try:
        logger.debug("Attempting Selenium scraping...")
        
        # Initialize Chrome WebDriver
        logger.debug("Initializing Chrome WebDriver")
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        driver = webdriver.Chrome(options=options)
        
        try:
            # Navigate to BSE page
            driver.get("https://www.bseindia.com/corporates/Forth_Results.html")
            
            # Wait for table data to load
            logger.debug("Waiting for table data to load...")
            wait = WebDriverWait(driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".breadcrumbarea table tbody tr")))
            
            # Find main div and table
            main_div = driver.find_element(By.CLASS_NAME, 'breadcrumbarea')
            table = main_div.find_element(By.TAG_NAME, 'table')
            
            # Get table text
            data_text = table.text
            logger.debug(f"Raw table text length: {len(data_text)}")
            
            # Split into lines and filter empty ones
            lines = [line.strip() for line in data_text.split('\n') if line.strip()]
            logger.debug(f"Found {len(lines)} non-empty lines")
            
            if not lines:
                return jsonify({'success': True, 'data': []})
            
            # Parse the data - handle different possible formats
            results = []
            
            # Skip the header line (first line)
            for line in lines[1:]:
                # Split by whitespace, but be more careful with parsing
                parts = line.split()
                logger.debug(f"Processing line: '{line}' -> parts: {parts}")
                
                if len(parts) >= 3:
                    # BSE format: SecurityCode CompanyName ResultDate
                    # Example: "532873 HDIL 08 Sep 2025"
                    security_code = parts[0]
                    result_date = ' '.join(parts[-3:])  # Last 3 parts for date like "08 Sep 2025"
                    
                    # Everything in between is company name
                    company_parts = parts[1:-3] if len(parts) > 3 else [parts[1]]
                    company_name = ' '.join(company_parts)
                    
                    logger.debug(f"Parsed: Code={security_code}, Company='{company_name}', Date='{result_date}'")
                    
                    # Find NSE symbol using our enhanced mapping function
                    nse_symbol = find_nse_symbol(company_name)
                    
                    if nse_symbol:
                        results.append({
                            'company': company_name,
                            'nse_symbol': nse_symbol,
                            'result_date': result_date,
                            'bse_code': security_code
                        })
                        logger.debug(f"Added: {company_name} -> {nse_symbol}")
                    else:
                        logger.debug(f"Skipping {company_name}: Not found in NSE mapping")
        
        finally:
            driver.quit()
        
        logger.info(f"Scraped {len(results)} results using Selenium")
        
        # If Selenium didn't work or returned no results, try fallback BeautifulSoup method
        if not results:
            logger.debug("Trying fallback BeautifulSoup method...")
            url = "https://www.bseindia.com/corporates/Forth_Results.html"
            headers = {'User-Agent': ua.random}
            
            response = session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', class_='mGrid')
                if not table:
                    table = soup.find('table')
                
                if table:
                    rows = table.find_all('tr')[1:]  # Skip header
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 3:
                            company = cols[0].text.strip()
                            bse_code = cols[1].text.strip()
                            result_date = cols[2].text.strip()
                            
                            # Map to NSE symbol
                            nse_symbol = find_nse_symbol(company)
                            if nse_symbol:
                                results.append({
                                    'company': company,
                                    'nse_symbol': nse_symbol,
                                    'result_date': result_date,
                                    'bse_code': bse_code
                                })
        
        logger.info(f"Fetched {len(results)} NSE-listed upcoming results")
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        logger.error(f"Error fetching BSE results: {str(e)} with traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/health', methods=['GET'])
def health_check():
    logger.debug("Received GET request for /api/health")
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    try:
        logger.info("Starting Flask server on http://0.0.0.0:5000")
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Server startup failed: {str(e)} with traceback: {traceback.format_exc()}")