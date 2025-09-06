from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import os
from dotenv import load_dotenv
import logging

load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_earnings(symbol):
    """
    Your original scraping logic with quarter ordering fix
    """
    url = f"https://www.screener.in/company/{symbol.upper()}/consolidated/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise ValueError(f"Failed to fetch page for {symbol}: {response.status_code}")
        
        soup = BeautifulSoup(response.text, 'html.parser')
       
        # Extract Market Cap
        market_cap = None
        top_ratios = soup.find('ul', id='top-ratios')
        if top_ratios:
            for li in top_ratios.find_all('li'):
                text = li.text.strip()
                if 'Market Cap' in text:
                    match = re.search(r'₹\s*([\d,]+)\s*Cr.', text)
                    if match:
                        market_cap = match.group(1).replace(',', '')
                    break
        
        if not market_cap:
            raise ValueError("Market Cap not found")
       
        # Extract Quarterly Table
        section = soup.find('section', id='quarters')
        if not section:
            raise ValueError("Quarters section not found")
        
        table = section.find('table')
        if not table:
            raise ValueError("Data table not found")
        
        rows = table.find_all('tr')
        data = []
        for row in rows:
            cols = row.find_all(['td', 'th'])
            data.append([col.text.strip() for col in cols])
        
        quarters = data[0][1:]  # Original quarters from scraping
        metrics = []
        values = []
        
        for row in data[1:]:
            metric = row[0].rstrip(' +')
            if metric == 'Raw PDF':
                continue
            vals = []
            for v in row[1:]:
                if v == '':
                    vals.append(None)
                elif '%' in v:
                    vals.append(float(v.rstrip('%')))
                else:
                    try:
                        vals.append(float(v.replace(',', '')))
                    except ValueError:
                        vals.append(None)
            metrics.append(metric)
            values.append(vals)
       
        if len(values) < 10:
            raise ValueError("Unexpected table structure")
       
        # Find indices
        try:
            op_profit_idx = metrics.index('Operating Profit')
            opm_idx = metrics.index('OPM %')
            eps_idx = metrics.index('EPS in Rs')
            sales_idx = op_profit_idx - 2
        except ValueError as e:
            raise ValueError(f"Missing required metric: {e}")
       
        sales = [int(x) if x is not None else None for x in values[sales_idx]]
        op_profit = [int(x) if x is not None else None for x in values[op_profit_idx]]
        opm = [int(x) if x is not None else None for x in values[opm_idx]]
        eps = values[eps_idx]  # keep as float
       
        # Calculations (using original order)
        def calc_pct(current, prev):
            if prev == 0 or prev is None or current is None:
                return 'N/A'
            return int(round((current - prev) / abs(prev) * 100, 0))
        
        sales_qoq = ['N/A'] + [calc_pct(sales[i], sales[i-1]) for i in range(1, len(sales))]
        sales_yoy = ['N/A'] * 4 + [calc_pct(sales[i], sales[i-4]) for i in range(4, len(sales))]
       
        # Take last 3 quarters but then REVERSE to show latest first
        num_qtrs = 8
        if len(quarters) < num_qtrs:
            raise ValueError("Not enough quarters available")
        
        # Get last 3 quarters and reverse them (latest first)
        quarters_latest_first = quarters[-num_qtrs:][::-1]
        sales_latest_first = sales[-num_qtrs:][::-1]
        op_profit_latest_first = op_profit[-num_qtrs:][::-1]
        opm_latest_first = opm[-num_qtrs:][::-1]
        eps_latest_first = eps[-num_qtrs:][::-1]
        sales_qoq_latest_first = sales_qoq[-num_qtrs:][::-1]
        sales_yoy_latest_first = sales_yoy[-num_qtrs:][::-1]
       
        # Build response data with corrected order
        result = {
            'symbol': symbol.upper(),
            'marketCap': market_cap,
            'quarters': quarters_latest_first,  # Now Jun 2025, Mar 2025, Dec 2024
            'metrics': {
                'Sales': sales_latest_first,
                'Operating Profit': op_profit_latest_first,
                'OPM %': opm_latest_first,
                'EPS in Rs': eps_latest_first,
                'Sales YoY %': [f"+{x}%" if isinstance(x, int) and x > 0 else f"{x}%" if isinstance(x, int) else x for x in sales_yoy_latest_first],
                'Sales QoQ %': [f"+{x}%" if isinstance(x, int) and x > 0 else f"{x}%" if isinstance(x, int) else x for x in sales_qoq_latest_first]
            }
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error scraping {symbol}: {str(e)}")
        raise

@app.route('/api/stock/<symbol>', methods=['GET'])
def get_stock_data(symbol):
    """
    Get financial data for a single stock symbol
    """
    try:
        result = get_earnings(symbol)
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/stocks', methods=['POST'])
def get_multiple_stocks():
    """
    Get financial data for multiple stock symbols
    """
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
            results[symbol] = result
        except Exception as e:
            errors[symbol] = str(e)
            logger.error(f"Error processing {symbol}: {str(e)}")
    
    return jsonify({
        'success': True,
        'results': results,
        'errors': errors
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    """
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)