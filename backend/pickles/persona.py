"""
PicklesGPT Persona Module

Defines the Pickles trading AI persona with:
- Enhanced system prompt with CAPITALIZATION style
- RAG integration for book knowledge
- Market data tools
- Response formatting
"""

import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# =============================================================================
# PICKLES CORE IDENTITY
# =============================================================================

PICKLES_IDENTITY = """You are **Pickles**, a veteran derivatives and futures trader with 17+ years of experience in the markets.

## YOUR IDENTITY
- Name: Pickles (never break character, you ARE Pickles)
- Experience: 17+ years trading professionally
- Style: Direct, experienced, helpful but realistic about markets
- Core belief: Markets are always right; we must adapt to them

## YOUR TRADING PROFILE
- Primary: ES, NQ, RTY, NG, GC, VIX, CL, SPX, SPY, QQQ - mostly intraday
- Secondary: Theta & vega trades (selling PREMIUM is the edge)
- Rarely: Individual stocks (only mega caps if forced)
- Goal: 1% portfolio per week, always be learning
- After profits: Long-term buy & hold (stocks, dividends, bonds)

## THE HOLY GOSPEL (Your Core Trading Philosophy)
1. "Wait for your A+ SETUPS" - Never force trades
2. "Trade the CHART, not the BIAS" - Price action is truth
3. "Always take PROFITS off the table" - Secure gains

## HOW YOU THINK ABOUT TRADES
Every trade needs a well-constructed THESIS with:
- Clear ENTRY point
- Clear EXIT point (PROFIT TARGET)
- Clear STOP LOSS
- Expected DURATION
- RISK/REWARD ratio (minimum 2:1)

## YOUR CAPITALIZATION STYLE
You ALWAYS CAPITALIZE important trading terminology:
- SUPPORT, RESISTANCE, BREAKOUT, BREAKDOWN
- VOLUME, PRICE ACTION, MOMENTUM, TREND
- STOP LOSS, TAKE PROFIT, RISK/REWARD
- ENTRY, EXIT, THESIS, SETUP
- PREMIUM, THETA, DELTA, GAMMA, VEGA
- CALLS, PUTS, SPREADS, IRON CONDORS
- BULL, BEAR, CONSOLIDATION, REVERSAL

## YOUR COMMUNICATION STYLE
- Direct and experienced, not arrogant
- Use trading jargon naturally but explain when needed
- Occasionally humble: "There's always something that humbles me back into the classroom"
- Focus on RISK MANAGEMENT and DISCIPLINE above all
- Encourage waiting for the right SETUPS rather than forcing trades
- Never give specific financial advice - explain concepts, don't promise results

## CRITICAL RULES
1. NEVER guess or hallucinate prices - if you don't have real data, say so
2. NEVER give specific buy/sell recommendations without disclaimers
3. ALWAYS emphasize RISK MANAGEMENT
4. When referencing books, cite them by title and author
5. Be authentic - you've seen many cycles, you've been humbled, you've learned"""

# =============================================================================
# RAG CONTEXT TEMPLATE
# =============================================================================

RAG_CONTEXT_TEMPLATE = """
## KNOWLEDGE FROM YOUR TRADING LIBRARY
Based on your 17 years of study, here's relevant knowledge from your book collection:

{book_excerpts}

Use this knowledge to inform your response, but speak from experience - don't just quote."""

# =============================================================================
# MARKET DATA TEMPLATE
# =============================================================================

MARKET_DATA_TEMPLATE = """
## CURRENT MARKET DATA (Real-time)
{market_data}

Use this data to provide accurate, current information. NEVER guess prices."""

# =============================================================================
# SYSTEM PROMPT BUILDER
# =============================================================================

def build_pickles_prompt(
    user_message: str,
    context_messages: List[Dict] = None,
    book_excerpts: List[Dict] = None,
    market_data: Dict = None,
    user_memory: Dict = None
) -> str:
    """
    Build the full Pickles system prompt with RAG and market data.
    
    Args:
        user_message: The user's current question
        context_messages: Previous conversation messages
        book_excerpts: RAG results from book library
        market_data: Real-time market data
        user_memory: Persistent user facts
    
    Returns:
        Complete prompt string for LLM
    """
    prompt_parts = []
    
    # 1. Core identity
    prompt_parts.append(f"[System]\n{PICKLES_IDENTITY}")
    
    # 2. RAG context from books
    if book_excerpts and len(book_excerpts) > 0:
        excerpts_text = "\n\n".join([
            f"**{ex['metadata'].get('book_title', 'Unknown')}** by {ex['metadata'].get('author', 'Unknown')}:\n\"{ex['text'][:500]}...\""
            for ex in book_excerpts[:3]  # Top 3 results
        ])
        prompt_parts.append(RAG_CONTEXT_TEMPLATE.format(book_excerpts=excerpts_text))
        logger.info(f"📚 RAG: Added {len(book_excerpts)} book excerpts to prompt")
    
    # 3. Market data (if available)
    if market_data:
        market_text = format_market_data(market_data)
        prompt_parts.append(MARKET_DATA_TEMPLATE.format(market_data=market_text))
        logger.info(f"📊 Market: Added real-time data to prompt")
    
    # 4. User memory (persistent facts)
    if user_memory and user_memory.get('facts'):
        facts = user_memory['facts']
        if len(facts) > 0:
            facts_text = "\n".join([f"- {fact['fact']}" for fact in facts[-10:]])
            prompt_parts.append(f"\n[User Background - Things to remember about this user]\n{facts_text}")
    
    # 5. Conversation history
    if context_messages and len(context_messages) > 0:
        prompt_parts.append("\n[Conversation History]")
        for msg in context_messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if role == 'user':
                prompt_parts.append(f"User: {content}")
            elif role == 'assistant':
                prompt_parts.append(f"Pickles: {content}")
            elif role == 'system':
                prompt_parts.append(f"[Context]: {content}")
    
    # 6. Current message
    prompt_parts.append(f"\nUser: {user_message}")
    prompt_parts.append("\nPickles:")
    
    return "\n".join(prompt_parts)


def format_market_data(data: Dict) -> str:
    """Format market data for prompt inclusion."""
    lines = []
    
    if 'stocks' in data:
        for symbol, info in data['stocks'].items():
            price = info.get('price', 'N/A')
            change = info.get('change_percent', 0)
            direction = "🟢" if change >= 0 else "🔴"
            lines.append(f"{symbol}: ${price} ({direction} {change:+.2f}%)")
    
    if 'indices' in data:
        for symbol, info in data['indices'].items():
            price = info.get('price', 'N/A')
            change = info.get('change_percent', 0)
            direction = "🟢" if change >= 0 else "🔴"
            lines.append(f"{symbol}: {price} ({direction} {change:+.2f}%)")
    
    if 'crypto' in data:
        for symbol, info in data['crypto'].items():
            price = info.get('price', 'N/A')
            change = info.get('change_24h', 0)
            direction = "🟢" if change >= 0 else "🔴"
            lines.append(f"{symbol}: ${price:,.2f} ({direction} {change:+.2f}% 24h)")
    
    return "\n".join(lines) if lines else "No market data available"


# =============================================================================
# KEYWORD EXTRACTION FOR RAG
# =============================================================================

# Trading keywords that should trigger book search
TRADING_KEYWORDS = [
    # Strategies
    'strategy', 'setup', 'pattern', 'trade', 'entry', 'exit',
    'breakout', 'breakdown', 'reversal', 'trend', 'momentum',
    
    # Risk management
    'stop loss', 'risk', 'position size', 'money management',
    
    # Technical analysis
    'support', 'resistance', 'moving average', 'rsi', 'macd',
    'fibonacci', 'bollinger', 'volume', 'candlestick', 'chart',
    
    # Options
    'option', 'call', 'put', 'spread', 'iron condor', 'butterfly',
    'theta', 'delta', 'gamma', 'vega', 'premium', 'volatility', 'iv',
    
    # Psychology
    'psychology', 'discipline', 'emotion', 'fear', 'greed', 'mindset',
    
    # Market types
    'futures', 'forex', 'stock', 'etf', 'index', 'commodity',
    
    # Books/authors
    'book', 'recommend', 'learn', 'study', 'read',
]

def should_search_books(message: str) -> bool:
    """
    Determine if a message should trigger book RAG search.
    """
    message_lower = message.lower()
    
    # Check for trading keywords
    for keyword in TRADING_KEYWORDS:
        if keyword in message_lower:
            return True
    
    # Check for question patterns about trading
    question_patterns = [
        'how do i', 'what is', 'explain', 'tell me about',
        'best way to', 'should i', 'when to',
    ]
    for pattern in question_patterns:
        if pattern in message_lower:
            # Only if combined with trading context
            if any(kw in message_lower for kw in ['trade', 'market', 'stock', 'option', 'futures']):
                return True
    
    return False


def extract_search_query(message: str) -> str:
    """
    Extract the core search query from user message for RAG.
    """
    # For now, just clean and return the message
    # Could be enhanced with keyword extraction
    cleaned = message.strip()
    
    # Remove common filler words
    fillers = ['please', 'can you', 'could you', 'i want to know', 'tell me']
    for filler in fillers:
        cleaned = cleaned.lower().replace(filler, '')
    
    return cleaned.strip()


# =============================================================================
# MARKET SYMBOL DETECTION
# =============================================================================

# Common market symbols
STOCK_SYMBOLS = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'GOOGL', 'META', 'AMD', 'NFLX']
INDEX_SYMBOLS = ['SPX', 'NDX', 'DJI', 'VIX', 'RUT']
FUTURES_SYMBOLS = ['ES', 'NQ', 'RTY', 'CL', 'GC', 'NG', 'ZB', 'ZN']
CRYPTO_SYMBOLS = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'ADA']

def extract_symbols(message: str) -> Dict[str, List[str]]:
    """
    Extract mentioned market symbols from message.
    """
    message_upper = message.upper()
    
    found = {
        'stocks': [],
        'indices': [],
        'futures': [],
        'crypto': []
    }
    
    for sym in STOCK_SYMBOLS:
        if sym in message_upper:
            found['stocks'].append(sym)
    
    for sym in INDEX_SYMBOLS:
        if sym in message_upper:
            found['indices'].append(sym)
    
    for sym in FUTURES_SYMBOLS:
        if sym in message_upper:
            found['futures'].append(sym)
    
    for sym in CRYPTO_SYMBOLS:
        if sym in message_upper:
            found['crypto'].append(sym)
    
    return found
