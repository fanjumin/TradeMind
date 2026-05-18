# Alpha Evol 集成说明

此文档说明如何将后端 Skill 的数据接口与前端 `Alpha Evol` 可视化界面对接。前端模板位于 `platform/templates/skills/alpha-evol.html`，前端静态资源位于 `platform/static/skills/`。

## 前端挂载
- 模板默认从 `/static/skills/alpha-evol.sample.json` 读取示例数据并自动初始化。要挂载到真实接口，可在页面容器上添加 `data-api` 属性：

  示例：

  <div id="alpha-evol" data-api="/api/skills/alpha-evol?symbol=300750.SZ"></div>

或通过 JS 手动初始化：

  <script>AlphaEvol.init('#alpha-evol')</script>

## 后端 API 说明
- 推荐端点：`GET /api/skills/alpha-evol?symbol={symbol}`
- 返回 JSON Content-Type: `application/json`

### 返回字段（示例）
{
  "level": 1,
  "exp": 12,
  "exp_next": 100,
  "ability_scores": {
    "technical": 0.48,
    "fundamental": 0.32,
    "sentiment": 0.22,
    "risk_control": 0.30,
    "execution": 0.26
  },
  "evolution_log": [
    {"ts":"2026-05-16T10:05:00","note":"完成回测，技术+0.8%","delta":{"technical":0.008}}
  ],
  "analysis": {
    "symbol":"300750.SZ",
    "title":"宁德时代 — 震荡突破",
    "summary":"短线多头，注意回撤支持位 230 元",
    "buy_signals":[{"type":"breakout","price":240,"prob":0.62}],
    "sell_signals":[]
  }
}

字段说明：
- `level` (int)：当前等级
- `exp` (number)：当前经验值
- `exp_next` (number)：升级所需经验
- `ability_scores` (object)：五项能力分数，0-1
- `evolution_log` (array)：时间排序的进化条目（`ts` ISO8601、`note`、可选 `delta`）
- `analysis` (object)：本次股票分析内容（`title`、`summary`、`buy_signals`、`sell_signals`、可选 `kline` 数据）

## 前端兼容 & 性能建议
- 雷达图使用 ECharts；后端仅需返回 `ability_scores` 数值，前端负责渲染与过渡。
- 若需要 K 线图，请在 `analysis.kline` 中提供标准 OHLCV 数组（时间、开、高、低、收、量），前端可用 ECharts K 线组件渲染。

Alpha Evol 集成说明

目的：说明后端 Skill 如何返回 JSON 数据，以及前端如何调用 `initAlphaEvol` / `updateAlphaEvol` 挂载到 `platform/templates/skills/alpha-evol.html`。

JSON 结构示例：

{
  "symbol": "600519",
  "timestamp": "2026-05-17T12:34:56Z",
  "level": 3,
  "exp": 420,
  "exp_to_next": 600,
  "gain": 120,
  "ability_scores": {
    "technical": 72,
    "fundamental": 65,
    "sentiment": 58,
    "risk": 70,
    "execution": 60
  },
  "evolution_log": [
    {"time":"2026-05-16T10:00:00Z","delta_exp":120,"desc":"完成技术因子优化，技术 +5"}
  ],
  "analysis": {
    "summary":"趋势向上，注意阻力位...",
    "signals":[{"type":"buy","price":230.5,"time":"2026-05-17T09:30:00Z","note":"突破20日均线"}],
    "kline": [
      // 可选：标准 OHLCV 数组，格式： [timestamp, open, high, low, close, volume]
      ["2026-05-01","10.2", "11.0", "10.0", "10.8", 120000]
    ]
  }
}

前端对接要点：
- 在页面加载时调用 `initAlphaEvol(containerSelector, jsonData)`。
- 若后端通过 websocket 或长轮询推送增量更新，调用 `updateAlphaEvol(jsonData)`，仅需包含发生变化的字段（如 `ability_scores`、`level`、`exp`、`evolution_log`、`analysis`）。
- 若平台已有 K 线渲染函数（如 `updateChart(klineData)`），Alpha Evol 会优先尝试调用该函数；否则回退到内置 ECharts K 线渲染。
- `analysis.kline` 推荐提供 ISO 日期字符串或时间戳作为第一列，后端可直接传 `unified_app` 中生成的 `kline` 数组。

性能与降级：
- 粒子与动画会在页面不可见时自动暂停。移动端可通过传入 `mobile:true` 标志在后端或前端禁用粒子和部分视觉效果。

移动端降级：
- 如果后端检测到客户端为移动设备，建议在返回的 JSON 中加入 `config.mobile: true`，示例如下：

```
{
  "level":2,
  "exp":120,
  "config": { "mobile": true }
}
```

前端收到包含 `config.mobile` 的数据会自动禁用粒子动画和部分视觉效果以节省性能。

示例：后端 Flask 路由返回 JSON，并在模板中直接注入：

```python
# Flask 示例
@app.route('/alpha-evol/<symbol>')
def alpha_evol(symbol):
    data = compute_alpha_evol(symbol)  # 返回上面的 JSON 结构
    return render_template('skills/alpha-evol.html', initial_data=json.dumps(data))
```

在模板中，可将模板变量注入并调用 `initAlphaEvol`：

```html
<script>
  const initial = {{ initial_data|safe }};
  initAlphaEvol('#alpha-evol-root', initial);
</script>
```

备注：文件路径
- 模板：platform/templates/skills/alpha-evol.html
- 静态资源：platform/static/skills/alpha-evol.css, alpha-evol.js
- 集成说明：platform/static/skills/ALPHA_EVOL_INTEGRATION.md

- 建议后端压缩常用字段，避免返回大量历史数据。前端采用懒加载（IntersectionObserver）。移动端可通过 `?mobile=1` 返回精简数据。

## 静态资源与文件位置
- 模板：`platform/templates/skills/alpha-evol.html`
- 样式：`platform/static/skills/alpha-evol.css`
- 脚本：`platform/static/skills/alpha-evol.js`
- 示例数据：`platform/static/skills/alpha-evol.sample.json`
- 头像占位：`platform/static/skills/images/avatar_lv1.svg`（`avatar_lv5.svg`、`avatar_lv10.svg`）

## 部署与集成步骤（简要）
1. 将前端文件放到平台静态目录（已完成）。
2. 在后端实现 `GET /api/skills/alpha-evol`，返回符合上述 JSON。可复用 Skill 的分析结果生成等级/经验与增益。
3. 在需要展示的页面引入模板或通过 iframe 嵌入，并设置 `data-api` 指向后端接口。
4. 若使用 CDN，请将 `echarts.min.js` 引入至平台公共静态库或模板头部。

如需我编写后端示例视图（Flask/Quart/FastAPI）或生成 K 线渲染示例，请告诉我偏好框架，我会继续实现。
