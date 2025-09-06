import React, { useState, useCallback } from 'react';
import { Search, Upload, TrendingUp, X, AlertCircle, Loader } from 'lucide-react';

const StockScreenerApp = () => {
  const [symbols, setSymbols] = useState(['RELIANCE']);
  const [inputSymbol, setInputSymbol] = useState('');
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState({});
  const [errors, setErrors] = useState({});

  const addSymbol = () => {
    if (inputSymbol.trim() && !symbols.includes(inputSymbol.toUpperCase().trim())) {
      setSymbols([...symbols, inputSymbol.toUpperCase().trim()]);
      setInputSymbol('');
    }
  };

  const removeSymbol = (symbolToRemove) => {
    setSymbols(symbols.filter(s => s !== symbolToRemove));
    // Clean up related data
    const newResults = { ...results };
    const newErrors = { ...errors };
    const newLoading = { ...loading };
    delete newResults[symbolToRemove];
    delete newErrors[symbolToRemove];
    delete newLoading[symbolToRemove];
    setResults(newResults);
    setErrors(newErrors);
    setLoading(newLoading);
  };

  const analyzeStock = useCallback(async (symbol) => {
    setLoading(prev => ({ ...prev, [symbol]: true }));
    setErrors(prev => ({ ...prev, [symbol]: null }));

    try {
      const response = await fetch(`http://localhost:5000/api/stock/${symbol}`);
      const data = await response.json();
      
      if (data.success) {
        setResults(prev => ({ ...prev, [symbol]: data.data }));
      } else {
        throw new Error(data.error || 'Failed to fetch stock data');
      }
    } catch (error) {
      setErrors(prev => ({ ...prev, [symbol]: error.message }));
    } finally {
      setLoading(prev => ({ ...prev, [symbol]: false }));
    }
  }, []);

  const analyzeAllStocks = async () => {
    // For better performance, use the batch endpoint for multiple stocks
    if (symbols.length > 1) {
      // Set loading state for all symbols
      const loadingState = {};
      symbols.forEach(symbol => {
        loadingState[symbol] = true;
      });
      setLoading(loadingState);
      
      // Clear previous errors
      setErrors({});

      try {
        const response = await fetch('http://localhost:5000/api/stocks', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ symbols }),
        });
        
        const data = await response.json();
        
        if (data.success) {
          setResults(prev => ({ ...prev, ...data.results }));
          if (data.errors && Object.keys(data.errors).length > 0) {
            setErrors(prev => ({ ...prev, ...data.errors }));
          }
        } else {
          throw new Error('Failed to analyze stocks');
        }
      } catch (error) {
        // Set error for all symbols if batch request fails
        const errorState = {};
        symbols.forEach(symbol => {
          errorState[symbol] = error.message;
        });
        setErrors(errorState);
      } finally {
        // Clear loading state for all symbols
        const clearedLoading = {};
        symbols.forEach(symbol => {
          clearedLoading[symbol] = false;
        });
        setLoading(clearedLoading);
      }
    } else {
      // For single symbol, use the individual endpoint
      symbols.forEach(symbol => {
        analyzeStock(symbol);
      });
    }
  };

  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (file && file.type === 'text/csv') {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const csv = e.target.result;
          const lines = csv.split('\n');
          const headers = lines[0].split(',');
          const symbolIndex = headers.findIndex(h => h.toLowerCase().includes('symbol'));
          
          if (symbolIndex !== -1) {
            const newSymbols = lines.slice(1)
              .map(line => line.split(',')[symbolIndex])
              .filter(symbol => symbol && symbol.trim())
              .map(symbol => symbol.trim().toUpperCase());
            
            setSymbols([...new Set([...symbols, ...newSymbols])]);
          }
        } catch (error) {
          console.error('Error parsing CSV:', error);
        }
      };
      reader.readAsText(file);
    }
  };

  const formatNumber = (num) => {
    if (num === null || num === undefined) return 'N/A';
    if (typeof num === 'string') return num;
    return num.toLocaleString('en-IN');
  };

  const getGrowthColor = (value) => {
    if (typeof value !== 'string') return 'text-gray-400';
    if (value.includes('+')) return 'text-green-400';
    if (value.includes('-')) return 'text-red-400';
    return 'text-gray-400';
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 text-white">
      {/* Header */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-blue-600/20 to-purple-600/20"></div>
        <div className="relative px-6 py-12 text-center">
          <h1 className="text-5xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent mb-4">
            Screener Insights
          </h1>
          <p className="text-xl text-gray-300 max-w-2xl mx-auto">
            Comprehensive financial analysis for Indian stocks - Market Cap, Sales Growth, Profitability, and more
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-6xl mx-auto px-6 pb-12">
        {/* Input Section */}
        <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl p-8 mb-8 border border-slate-700/50">
          <div className="flex items-center gap-3 mb-6">
            <TrendingUp className="text-blue-400" size={24} />
            <h2 className="text-2xl font-semibold">Stock Screener Insights</h2>
          </div>
          <p className="text-gray-400 mb-6">Analyze financial metrics for Indian stocks</p>

          {/* Symbol Input */}
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="flex-1 relative">
                <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
                <input
                  type="text"
                  value={inputSymbol}
                  onChange={(e) => setInputSymbol(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && addSymbol()}
                  placeholder="Enter stock symbol (e.g., RELIANCE, TCS, INFY)"
                  className="w-full pl-12 pr-4 py-4 bg-slate-700/50 border border-slate-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 text-white placeholder-gray-400"
                />
              </div>
              <button
                onClick={addSymbol}
                className="px-6 py-4 bg-blue-600 hover:bg-blue-700 rounded-xl transition-colors font-medium"
              >
                Add
              </button>
            </div>

            <div className="text-center text-gray-400">OR</div>

            {/* File Upload */}
            <div className="border-2 border-dashed border-slate-600 rounded-xl p-6 text-center hover:border-blue-500 transition-colors">
              <Upload className="mx-auto mb-3 text-gray-400" size={32} />
              <label className="cursor-pointer">
                <span className="text-blue-400 hover:text-blue-300 font-medium">Upload CSV File</span>
                <input
                  type="file"
                  accept=".csv"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>
              <p className="text-sm text-gray-500 mt-2">
                Upload a CSV file with stock symbols (looks for 'SYMBOL' column or uses first column)
              </p>
              <p className="text-sm mt-2">Note: Connected to Flask backend at http://localhost:5000</p>
            </div>
          </div>

          {/* Symbols List */}
          {symbols.length > 0 && (
            <div className="mt-6">
              <h3 className="text-lg font-medium mb-3">Symbols to analyze:</h3>
              <div className="flex flex-wrap gap-2 mb-4">
                {symbols.map(symbol => (
                  <span
                    key={symbol}
                    className="inline-flex items-center gap-2 bg-slate-700 px-3 py-2 rounded-lg text-sm"
                  >
                    {symbol}
                    <button
                      onClick={() => removeSymbol(symbol)}
                      className="hover:text-red-400 transition-colors"
                    >
                      <X size={16} />
                    </button>
                  </span>
                ))}
              </div>
              <button
                onClick={analyzeAllStocks}
                className="w-full py-4 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 rounded-xl transition-all duration-200 font-medium text-lg flex items-center justify-center gap-2"
              >
                <Search size={20} />
                Analyze {symbols.length} Stock{symbols.length > 1 ? 's' : ''}
              </button>
            </div>
          )}
        </div>

        {/* Results Section */}
        {symbols.map(symbol => (
          <div key={symbol} className="mb-8">
            {loading[symbol] && (
              <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl p-8 border border-slate-700/50">
                <div className="flex items-center justify-center gap-3">
                  <Loader className="animate-spin text-blue-400" size={24} />
                  <span className="text-lg">Analyzing {symbol}...</span>
                </div>
              </div>
            )}

            {errors[symbol] && (
              <div className="bg-red-900/30 border border-red-700/50 rounded-2xl p-6 mb-4">
                <div className="flex items-center gap-3">
                  <AlertCircle className="text-red-400" size={24} />
                  <div>
                    <h3 className="text-xl font-semibold text-red-300">Error for {symbol}</h3>
                    <p className="text-red-200">{errors[symbol]}</p>
                  </div>
                </div>
              </div>
            )}

            {results[symbol] && (
              <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl p-8 border border-slate-700/50">
                <div className="flex justify-between items-center mb-6">
                  <h2 className="text-3xl font-bold">{symbol}</h2>
                  <div className="text-right">
                    <p className="text-gray-400 text-sm">Market Cap</p>
                    <p className="text-2xl font-bold text-blue-400">
                      ₹{formatNumber(results[symbol].marketCap)} Cr.
                    </p>
                  </div>
                </div>

                {/* Metrics Table */}
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-slate-600">
                        <th className="text-left py-4 px-2 text-gray-300 font-medium">Metric</th>
                        {results[symbol].quarters.map(quarter => (
                          <th key={quarter} className="text-center py-4 px-4 text-gray-300 font-medium">
                            {quarter}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(results[symbol].metrics).map(([metric, values]) => (
                        <tr key={metric} className="border-b border-slate-700/30 hover:bg-slate-700/20 transition-colors">
                          <td className="py-4 px-2 font-medium text-gray-200">{metric}</td>
                          {values.map((value, idx) => (
                            <td key={idx} className="text-center py-4 px-4">
                              {metric.includes('YoY %') || metric.includes('QoQ %') ? (
                                <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                                  getGrowthColor(value) === 'text-green-400' 
                                    ? 'bg-green-900/30 text-green-400 border border-green-700/50'
                                    : getGrowthColor(value) === 'text-red-400'
                                    ? 'bg-red-900/30 text-red-400 border border-red-700/50'
                                    : 'bg-gray-800/50 text-gray-400 border border-gray-600/50'
                                }`}>
                                  {value}
                                </span>
                              ) : (
                                <span className="text-gray-200">{formatNumber(value)}</span>
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Quick Insights */}
                <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-slate-700/30 rounded-xl p-4">
                    <h4 className="text-sm text-gray-400 mb-1">Latest Sales</h4>
                    <p className="text-xl font-bold">₹{formatNumber(results[symbol].metrics['Sales'][0])} Cr.</p>
                  </div>
                  <div className="bg-slate-700/30 rounded-xl p-4">
                    <h4 className="text-sm text-gray-400 mb-1">Latest OPM</h4>
                    <p className="text-xl font-bold">{results[symbol].metrics['OPM %'][0]}%</p>
                  </div>
                  <div className="bg-slate-700/30 rounded-xl p-4">
                    <h4 className="text-sm text-gray-400 mb-1">Latest EPS</h4>
                    <p className="text-xl font-bold">₹{formatNumber(results[symbol].metrics['EPS in Rs'][0])}</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Empty State */}
        {Object.keys(results).length === 0 && !Object.keys(loading).some(k => loading[k]) && (
          <div className="text-center py-16">
            <TrendingUp className="mx-auto mb-4 text-gray-500" size={64} />
            <h3 className="text-2xl font-semibold text-gray-400 mb-2">Ready to Analyze</h3>
            <p className="text-gray-500">Add stock symbols and click "Analyze" to see financial insights</p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="text-center py-8 text-gray-500 border-t border-slate-700/50">
        <p>© 2025 Screener Insights - Financial analysis made simple</p>
        <p className="text-sm mt-2">Note: Connected to Flask backend at http://localhost:5000</p>
      </div>
    </div>
  );
};

export default StockScreenerApp;