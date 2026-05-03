# TradeMind

> A-Stock Analysis Tool — A股分析工具，一站式大盘看板、个股分析、策略回测、模拟交易、本地备份

**v0.1.0** | [CHANGELOG](CHANGELOG.md) | [使用手册](docs/USER_GUIDE.md) | [API 文档](docs/API.md)

---

## 快速开始

```bash
pip install -r requirements.txt
python3 unified_app.py --port 8081
```

打开 http://localhost:8081 即可使用。

---

## 11 个页面一览

| 页面 | 路由 | 功能 |
|------|------|------|
| 大盘看板 | `/` | 指数行情、自选股、行业排行 |
| 股票分析 | `/analyze` | 技术面、基本面、资金流、AI 预测 |
| 策略市场 | `/strategies` | 多策略对比、参数优化、回测 |
| 模拟交易 | `/trade` | 创建组合、买入卖出、盈亏分析 |
| 关于平台 | `/about` | 产品介绍、功能介绍 |
| 订阅 | `/subscribe` | 套餐选择、定价方案 |
| API 文档 | `/docs` | REST API 接口文档 |
| 教程 | `/tutorial` | 使用指南、操作说明 |
| 联系 | `/contact` | 客服联系方式 |
| 本地备份 | `/backup` | experience.db 自动备份、下载、回退 |
| 版本管理 | `/update` | 检查更新、下载源码、版本回退 |

---

## 功能特点

- **大盘概览**: 上证/深证/创业板/科创50 等指数实时行情
- **个股分析**: 技术指标(均线/RSI/KDJ/Bollinger) + 基本面评分 + 资金流向
- **AI 预测**: 基于技术指标的短期价格走势预测
- **多策略回测**: 10+ 内置策略，支持参数优化和 Monte Carlo 模拟
- **模拟交易**: 创建投资组合，模拟买入卖出，跟踪盈亏
- **选股器**: 预设策略筛选 + 自定义条件选股
- **实时扫描**: 定时扫描选股，变化检测 + 微信推送
- **行情预警**: 57 种预警条件，覆盖技术面/基本面/量价
- **本地备份**: Watchdog 每 10 秒检测 experience.db 变化，自动备份到本地
- **企业微信推送**: 备份完成后自动发送通知到企业微信

---

## CLI 使用

```bash
python main.py 000001           # 分析个股
python main.py --market          # 大盘概览
python main.py --sectors 10      # 行业排行
python main.py --report 600519   # 完整分析报告
python main.py --backtest 000001 # 回测
```

---

## 目录结构

```
TradeMind/
  unified_app.py        -- 唯一服务入口 (port 8081)
  backup_module.py      -- 备份 + 推送逻辑
  main.py               -- CLI 入口
  skill.py              -- Python API 入口
  version.py            -- 版本号
  VERSION               -- 版本文件
  web/
    app.py              -- Web 路由
    api_v1.py           -- REST API v1 蓝本
    templates/
      base.html         -- 统一基础模板
      dashboard.html    -- 大盘看板
      analyze.html      -- 股票分析
      strategies.html   -- 策略市场
      trade.html        -- 模拟交易
      about.html        -- 关于平台
      subscribe.html    -- 订阅
      docs.html         -- API 文档
      tutorial.html     -- 教程
      contact.html      -- 联系
      backup.html       -- 本地备份
  analysis/             -- 分析层
    technical.py        -- 技术指标
    scoring.py          -- 综合评分
    sentiment.py        -- 新闻情绪
    predict.py          -- AI 预测
    factors.py          -- 因子分析
    financials.py       -- 财务数据
    llm_advisor.py      -- LLM 智能分析
  data/                 -- 数据获取层
    price.py            -- 行情数据
    index.py            -- 指数数据
    sector.py           -- 行业板块
    fund.py             -- 资金流向
    basic.py            -- 基础信息
    news.py             -- 新闻数据
  alert_push.py         -- 企业微信推送
  alerts.py             -- 预警引擎
  backtest.py           -- 回测引擎
  screener.py           -- 选股器
  sim_trade.py          -- 模拟交易
  portfolio.py          -- 投资组合
  strategy_market.py    -- 策略市场
  scanner_daemon.py     -- 定时扫描
  visualization.py      -- 图表生成
  report.py             -- 报告生成
  predict.py            -- 价格预测
