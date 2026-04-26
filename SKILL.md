# TradeMind Skill

A-Stock analysis skill. Provides technical analysis, fund flow tracking, comprehensive fundamental scoring, and market overview.

## Data Sources
- **Tencent** qt.gtimg.cn: Real-time price, PE, PB, turnover rate, volume ratio, amplitude
- **Sina** quotes.sina.cn: Historical K-line (datalen=100, daily), MA5/10/20/60
- **Baostock**: ROE, net profit margin, gross margin, EPS, revenue, YOY growth data

## Fundamental Scoring (0-100)

| Component | Max Pts | Criteria |
|-----------|---------|----------|
| PE Ratio | 15 | <15:15pts, 15-25:12pts, 25-40:8pts, 40-60:3pts, >60:0pts |
| PB Ratio | 10 | <1.5:10pts, 1.5-3:8pts, 3-6:5pts, >6:1pt |
| ROE | 25 | >=20%:25pts, >=15%:20pts, >=10%:15pts, >=5%:8pts, >0:3pts |
| Net Margin | 15 | >=30%:15pts, >=15%:12pts, >=8%:8pts, >=3%:4pts |
| Growth | 20 | Combined YOY net income + EPS growth (10pts each) |
| Turnover | 10 | 1-5%:10pts, 5-10%:8pts, 0.3-1%:6pts, >10%:5pts |

## Signal Thresholds
- >=70: 强烈买入 (strong_buy)
- >=55: 买入 (buy)
- >=40: 持有 (hold)
- >=25: 减仓 (reduce)
- <25: 回避 (avoid)

## Usage

### CLI
```bash
python main.py 000001           # Analyze stock (JSON)
python main.py --market          # Market overview
python main.py --sectors [N]     # Sector ranking
python main.py --report 600519   # Full text report
```

### Python API
```python
from skill import StockAnalysisSkill
skill = StockAnalysisSkill()
result = skill.analyze_stock("000001")  # JSON string
```

## Output Format (JSON)
```json
{
  "stock": "000001",
  "trend": "downtrend",
  "fund_flow_proxy": 0.0,
  "basic_score": 58,
  "total_score": 37,
  "signal": "reduce",
  "signal_cn": "减仓",
  "reasons": ["估值便宜(PE<15)", "市净率极低(PB<1.5)", ...]
}
```

## Location
/home/guxiao/projects/Skills Code/TradeMind/

## Venv
/home/guxiao/.hermes/stock-agent-venv/bin/python3
