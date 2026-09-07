"""stock-tips-system — a self-learning Indian stock-tip vetting pipeline.

Layers
------
data/       prices (Yahoo chart API), live quotes (Moneycontrol), fundamentals (Screener.in), symbol master (NSE)
sources/    tip gatherers (Google News, listing pages, Chartink scans, Telegram) + text→structured-tip extraction
analysis/   technical analysis, target/stop-loss planning, TA + fundamentals scoring, composite
portfolio/  paper ledger with stepped exits, time stops, confidence-weighted allocation
learning/   per-source confidence updates from realised outcomes, lessons journal
report.py   markdown reports for the morning / EOD runs
cli.py      `python -m stocktips <command>`
"""
__version__ = "0.1.0"
