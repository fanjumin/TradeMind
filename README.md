# TradeMind

A股股票分析工具 - 个股、行业、大盘趋势分析

## 功能
- **个股分析**: 技术面 + 基本面 + 资金流综合评分
- **大盘概览**: 上证/深证/创业板/科创50等指数状态
- **行业排行**: 领涨/领跌行业板块排行
- **完整报告**: 格式化文本分析报告

## 安装
```bash
pip install akshare pandas numpy
```

## 使用

### 命令行
```bash
python main.py 000001           # 分析个股
python main.py --market          # 大盘概览
python main.py --sectors 10      # 行业排行
python main.py --report 600519   # 完整报告
```

### Python 调用
```python
from skill import StockAnalysisSkill
skill = StockAnalysisSkill()

# 个股分析
result = skill.analyze_stock("000001")

# 大盘
market = skill.market_overview()

# 行业
sectors = skill.sector_ranking(10)
```

## 目录结构
```
TradeMind/
  data/          - 数据获取层 (price, sector, index, basic, fund)
  analysis/      - 分析层 (technical, scoring)
  skill.py       - Skill入口
  main.py        - CLI入口
  report.py      - 报告生成
  SKILL.md       - Skill描述
```
