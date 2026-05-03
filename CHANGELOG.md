# Changelog

## v0.1.0 (2026-05-03)

### Added
- 统一 11 页面 UI: 所有页面继承 base.html，共用 nav 导航栏和暗色主题
- 本地备份管理: /backup 页面 (Watchdog 自动备份 + 下载/回退/删除/上传)
- 企业微信推送: 备份后自动推送通知 (可启用/禁用/测试)
- 单端口架构: TradeMind Web(:5000) + API(:8081) + sync(:8766) 合并为 unified_app.py(:8081)
- 版本管理: VERSION 文件、version.py、CHANGELOG.md

### Changed
- API 产品页面 (/about /subscribe /docs /tutorial /contact) 合并到主服务
- 所有模板改为继承 base.html，样式统一
- sync_server.py 的备份/推送功能合并到 unified_app.py
- 推送路径: sync → localhost:8081/api/alert/send (不再直连远程)

### Removed
- sync_server.py (功能已合并)
- sync_server.html (功能已合并到 /backup 页面)

---

## 历史版本

- v2.6: Phase 1-3 complete — API/Financials/Factors/Scanner/StrategyMarket/MultiAsset/SimTrading/RetailFeatures
- feat: LLM-based sentiment analysis with local learning store
- feat: enhance tech indicators/backtest/alerts to close gaps with mainstream tools
- feat: Plotly interactive chart (Phase 1 visualization)
- feat: sentiment/news analysis module (t10)
- feat: complete TradeMind - backtest/predict/visualize/alerts
- feat: add RSI/KDJ/Bollinger/capital flow/industry/valuation
- feat: upgrade fundamental scoring with ROE, margins, growth
