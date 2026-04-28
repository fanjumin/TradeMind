# TradeMind vs 主流AI股票分析工具 — 差距分析
> 2026-04-28 | v2.4 | 30模块/11,271行

## TradeMind 当前能力总览

数据层: A股实时(腾讯) + 3年历史(baostock) + 社交情绪(股吧+LLM) + 行业PE/PB + 全球指数
分析层: 82指标 + 13K线形态 + 150+情绪词典 + LLM分析 + DCF/PEG + 100分评分
预测层: sklearn集成(RF+GBDT+Ridge 65-73%) + numpy LSTM v2 + LLM事件研判
策略层: 10策略回测 + 参数优化 + 蒙特卡洛 + A股成本模型
交互层: 30+CLI + Flask仪表盘 + Plotly 6面板 + 微信推送 + 5500股NL选股

## 竞品对比核心发现

### vs 国际商业 (Trade Ideas/TrendSpider/Tickeron $30-228/月)
- 超越: NL选股(竞品无)、社交情绪(竞品无)、LLM多层整合
- 持平: 技术指标深度、回测、告警
- 不及: 实时扫描(Holly AI全天候)、REST API、移动端