# TradeMind API 参考

> v0.1.0 | REST API | 基础路径: `http://localhost:8081`

---

## 市场数据

### 指数行情
```
GET /api/indices
```
返回 A股主要指数实时数据。

### 股票列表
```
GET /api/stocks
```
返回自选股列表及实时行情。

### 个股详情
```
GET /api/stock/<symbol>
```
参数: `symbol` - 股票代码 (如 000001, 600519)

### 个股技术指标
```
GET /api/stock/<symbol>/indicators
```
返回均线、RSI、KDJ、MACD、Bollinger 等技术指标。

### 分钟线数据
```
GET /api/minute/<symbol>
```

### 个股搜索
```
GET /api/search?q=<keyword>
```

---

## 资金流向

### 资金流数据
```
GET /api/screener/scan
GET /api/screener/query?min_price=...&max_pe=...
```

---

## 分析

### AI 预测
```
GET /api/predict/<symbol>
GET /api/predict/<symbol>/llm
```

### 情绪分析
```
GET /api/sentiment/<symbol>
GET /api/sentiment-social/<symbol>
```

### 综合分析
```
GET /api/full-analysis/<symbol>
```

### 图表
```
GET /api/chart/<symbol>
```

---

## 回测

### 标准回测
```
GET /api/backtest/<symbol>
```

### 参数优化回测
```
GET /api/backtest/<symbol>/optimize
```

---

## 投资组合

```
GET  /api/portfolio/list
POST /api/portfolio/create
GET  /api/portfolio/<id>
POST /api/portfolio/<id>/buy
POST /api/portfolio/<id>/sell
GET  /api/portfolio/<id>/analysis
```

---

## 自选股

```
GET  /api/watchlist/list
GET  /api/watchlist/<name>
POST /api/watchlist/create
POST /api/watchlist/<name>/add
POST /api/watchlist/<name>/remove
```

---

## 预警/推送

### 发送消息到企业微信
```
POST /api/alert/send
```
Body:
```json
{"message": "内容", "type": "text|markdown", "title": "标题"}
```

### 推送选股报告
```
GET /api/alert/push/screener?preset=<name>
GET /api/alert/push/stock/<symbol>
GET /api/alert/push/market
```

---

## 本地备份

```
GET  /api/backups              - 备份列表
POST /api/backup               - 手动备份
GET  /api/download/<name>      - 下载备份文件
POST /api/restore              - 回退到指定版本
DELETE /api/delete/<name>      - 删除备份
POST /api/upload               - 上传备份文件
```

### 推送配置

```
GET  /api/push_config          - 读取推送配置
POST /api/push_config          - 保存推送配置
POST /api/push_test            - 发送测试推送
```

---

## 版本管理

```
GET  /api/update/check         - 检查更新
GET  /api/update/download      - 下载源码
POST /api/update/apply         - 执行更新
POST /api/update/rollback      - 版本回退
POST /api/update/delete        - 清理旧版本
```

---

## 系统

```
GET /health                    - 健康检查
GET /api/backup_ping           - 备份模块状态
```

---

## 认证 (v1)

API v1 需要 API Key，通过 Blueprint 注册在 `/api/v1` 路径下:

```
GET /api/v1/
GET /api/v1/health
GET /api/v1/market/indices
GET /api/v1/stock/<symbol>
GET /api/v1/stock/<symbol>/technical
GET /api/v1/stock/<symbol>/full
GET /api/v1/screener/presets
GET /api/v1/screener/run/<preset>
POST /api/v1/backtest/<symbol>
...
```

---

## API Key 管理

```
GET  /api/v2/key/generate       - 生成免费 Key
GET  /api/admin/keys            - 列出所有 Key
POST /api/admin/gen_key         - 创建 Key (管理后台)
POST /api/admin/payment/create  - 创建支付订单
POST /api/admin/payment/confirm - 确认支付
```
