"""User-authorized mainstream, unleveraged US demonstration instruments.

Membership describes scope, not investment recommendations or a survivorship-free index.
"""

UNIVERSE = {
    'AAPL': {'name': 'Apple', 'kind': 'stock'},
    'MSFT': {'name': 'Microsoft', 'kind': 'stock'},
    'AMZN': {'name': 'Amazon', 'kind': 'stock'},
    'QQQ': {'name': 'Invesco QQQ Trust', 'kind': 'etf'},
    'SPY': {'name': 'SPDR S&P 500 ETF Trust', 'kind': 'etf'},
    'NVDA': {'name': 'NVIDIA', 'kind': 'stock'},
    'META': {'name': 'Meta Platforms', 'kind': 'stock'},
    'GOOG': {'name': 'Alphabet Class C', 'kind': 'stock'},
    'AVGO': {'name': 'Broadcom', 'kind': 'stock'},
    'TSLA': {'name': 'Tesla', 'kind': 'stock'},
    'AMD': {'name': 'Advanced Micro Devices', 'kind': 'stock'},
    'NFLX': {'name': 'Netflix', 'kind': 'stock'},
    'ORCL': {'name': 'Oracle', 'kind': 'stock'},
    'CRM': {'name': 'Salesforce', 'kind': 'stock'},
    'ADBE': {'name': 'Adobe', 'kind': 'stock'},
    'COST': {'name': 'Costco', 'kind': 'stock'},
    'WMT': {'name': 'Walmart', 'kind': 'stock'},
    'JPM': {'name': 'JPMorgan Chase', 'kind': 'stock'},
    'V': {'name': 'Visa', 'kind': 'stock'},
    'MA': {'name': 'Mastercard', 'kind': 'stock'},
    'UNH': {'name': 'UnitedHealth Group', 'kind': 'stock'},
    'XOM': {'name': 'Exxon Mobil', 'kind': 'stock'},
    'CVX': {'name': 'Chevron', 'kind': 'stock'},
    'BRK-B': {'name': 'Berkshire Hathaway Class B', 'kind': 'stock'},
    'LLY': {'name': 'Eli Lilly', 'kind': 'stock'},
    'ABBV': {'name': 'AbbVie', 'kind': 'stock'},
    'CAT': {'name': 'Caterpillar', 'kind': 'stock'},
    'HD': {'name': 'The Home Depot', 'kind': 'stock'},
    'PLTR': {'name': 'Palantir Technologies', 'kind': 'stock'},
    'VTI': {'name': 'Vanguard Total Stock Market ETF', 'kind': 'etf'},
    'DIA': {'name': 'SPDR Dow Jones Industrial Average ETF Trust', 'kind': 'etf'},
    'IWM': {'name': 'iShares Russell 2000 ETF', 'kind': 'etf'},
    'XLK': {'name': 'Technology Select Sector SPDR Fund', 'kind': 'etf'},
    'XLF': {'name': 'Financial Select Sector SPDR Fund', 'kind': 'etf'},
    'XLV': {'name': 'Health Care Select Sector SPDR Fund', 'kind': 'etf'},
    'XLE': {'name': 'Energy Select Sector SPDR Fund', 'kind': 'etf'},
    'SMH': {'name': 'VanEck Semiconductor ETF', 'kind': 'etf'},
    'SOXX': {'name': 'iShares Semiconductor ETF', 'kind': 'etf'},
    'GLD': {'name': 'SPDR Gold Shares', 'kind': 'etf'},
    'TLT': {'name': 'iShares 20+ Year Treasury Bond ETF', 'kind': 'etf'},
}

SYMBOLS = tuple(UNIVERSE)

EXCLUDED_SYMBOLS = {
    'GE': 'Yahoo encodes GE HealthCare/GE Vernova spinoffs as 1281:1000 and 1253:1000 '
          'split-like price adjustments. Spin-off accounting is not implemented; source '
          'bytes are preserved for inspection but GE is excluded from executable data.',
}
