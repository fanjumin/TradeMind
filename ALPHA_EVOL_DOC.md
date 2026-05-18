# Alpha Evol 可视化界面实现文档

**项目**: TradeMind (easykai.cn)  
**功能**: Alpha Evol 股票分析 Skill 的前端可视化进化界面  
**完成时间**: 2026-05-17 14:00:21 (CST)  
**提交记录**: `d1e1547` - feat: 完成Alpha Evol可视化界面实现  

## 目录
1. [实现概述](#实现概述)  
2. [文件结构](#文件结构)  
3. [技术栈](#技术栈)  
4. [数据流与接口](#数据流与接口)  
5. [组件说明](#组件说明)  
6. [样式与主题](#样式与主题)  
7. [响应式布局](#响应式布局)  
8. [性能考量](#性能考量)  
9. [后端对接指南](#后端对接指南)  
10. [使用示例](#使用示例)  
11. [未来改进方向](#未来改进方向)  

---  

## 实现概述
Alpha Evol 界面旨在以科幻金融风格直观展示股票分析 Skill（“Alpha Evol”）的成长过程。核心目标包括：
- 虚拟形象随等级进化  
- 能力雷达图动态反映五维能力分数  
- 经验条与进化日志展示成长轨迹  
- 分析结果区展示专业股票分析内容及买卖点  

界面设计为独立可复用组件，仅需容器选择器及后端返回的 JSON 数据即可初始化。  

## 文件结构
```
platform/
└─ static/
   └─ skills/
      ├─ alpha-evol.css          # 自定义样式（玻璃态、霓虹、动画）
      ├─ alpha-evol.js           # 核心逻辑：ECharts 初始化、数据渲染、更新函数
      └─ images/
         ├─ avatar_lv1.svg       # 等级 1-4 虚拟形象
         ├─ avatar_lv5.svg       # 等级 5-9 虚拟形象
         └─ avatar_lv10.svg      # 等级 10+ 虚拟形象
└─ templates/
   └─ skills/
      └─ alpha-evol.html         # 主模板：结构、占位符、示例初始化脚本
```
> 注：所有文件均已提交至 Git（`d1e1547`）。  

## 技术栈
| 技术 | 用途 |
|------|------|
| **Tailwind CSS** (`/static/css/tailwind.css`) | 基础实用类、响应式网格、暗色主题 |
| **ECharts 5** (`/static/libs/echarts.min.js`) | 能力雷达图、K线图（后备） |
| **原生 JavaScript ES6** | 数据处理、DOM 操作、动画（粒子） |
| **HTML5** | 语义化结构、可访问性属性 |

## 数据流与接口
### 后端期望返回的 JSON 结构
```json
{
  "symbol": "600519",                     // 股票代码（用于标题）
  "timestamp": "2026-05-17T10:00:00Z",    // 分析时间戳
  "level": 3,                             // 当前等级（整数）
  "exp": 340,                             // 当前经验值
  "exp_to_next": 500,                     // 升级所需经验
  "gain": 120,                            // 本次分析获得的经验（正数或负数）
  "ability_scores": {                     // 五维能力分数（0-100）
    "technical": 75,
    "fundamental": 68,
    "sentiment": 60,
    "risk": 72,
    "execution": 65
  },
  "evolution_log": [                      // 最近进化日志（时间倒序）
    {
      "time": "2026-05-17T09:30:00Z",
      "delta_exp": 120,
      "desc": "技术因子优化，技术 +5"
    }
  ],
  "analysis": {                           // 专业分析内容
    "summary": "短期趋势向上，注意前高阻力。",
    "signals": [                          // 买卖信号列表
      {
        "type": "buy",                    // buy / sell
        "price": 230.5,
        "time": "10:00",
        "note": "突破20日均线"
      }
    ],
    "kline": []                           // 可选：K线原始数据 [[time,open,high,low,close], ...]
  }
}
```
> **字段说明**：  
> - 所有字段均为可选，前端会使用默认值防止报错。  
> - `ability_scores` 中的键名必须与前端映射一致（见 `formatRadarData`）。  
> - `evolution_log` 中的 `time` 可为 ISO 字符串或时间戳。  

### 前端提供的全局函数
- `window.initAlphaEvol(containerSelector, jsonData)`  
  初始化组件。`containerSelector` 为 CSS 选择器或 DOM 节点；`jsonData` 为后端返回的完整数据对象。  
- `window.updateAlphaEvol(jsonData)`  
  增量更新。仅传入变化的字段，内部会合并至内部状态并重新渲染受影响部分。  

## 组件说明
### 布局（Desktop）
```
+--------------------------------------------------------------+
| 头像区        |   能力雷达图   |   经验条 & 进化日志          |
| (虚拟形象)    |                |                              |
|               +----------------+---------------------------+
|               |                |          分析结果区           |
|               |                |   (摘要, 买卖点, K线占位)    |
+--------------------------------------------------------------+
```
- **头像区**（左侧 1/3）：显示当前等级、虚拟形象图片（随等级切换）、轻微粒子背景（非移动端）。  
- **能力雷达图**（中上）：使用 ECharts 雷达图，五轴分别为技术分析、基本面、情绪分析、风险控制、执行力。  
- **经验条 & 进化日志**（中下）：经验进度条（渐变色）、本次获得经验、可滚动的进化日志列表。  
- **分析结果区**（底部）：股票代码与时间戳、分析摘要、买卖信号卡片（买入蓝/卖出红）、K线图占位（后备为简单 ECharts 蜡烛图）。  

### 移动端布局（≤768px）
- 整体切换为单列垂直流：头像 → 雷达图 → 经验条/日志 → 分析结果。  
- 头像尺寸缩小，粒子动画被禁用以节省性能。  

## 样式与主题
- **深色科幻金融风格**：  
  - 背景色：`#071026`（近黑深蓝）  
  - 玻璃态卡片：`background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); backdrop-filter: blur(8px);`  
  - 霓虹色彩：渐变从 `#00f6ff` (青) → `#7c4dff` (紫) → `#00ffa3` (绿) 用于文字、进度条等。  
- **动画**：  
  - 虚拟形象在等级≥3 时添加轻微旋转、放大及发光滤镜（`.evolved` 类）。  
  - 经验条宽度变化使用 CSS `transition` 实现平滑。  
  - 粒子背景（仅 Desktop）使用 `requestAnimationFrame` 绘制缓慢漂移的蓝紫色点。  

## 响应式布局
- 使用 Tailwind 的响应式前缀（`lg:`）实现栅格切换。  
- 移动端头像尺寸固定为 96px，以避免过大占用屏幕。  
- 日志区最大高度固定（`max-h-36`），超出后出现滚动条（自定义滚动条样式）。  

## 性能考量
1. **粒子动画**：仅在非移动端且页面可见时启用；监听 `visibilitychange` 暂停/恢复。  
2. **ECharts 实例**：雷达图与 K线图均只初始化一次，后续仅调用 `setOption` 更新数据。  
3. **DOM 更新**：渲染函数尽量复用元素，仅在必要时修改 `textContent` 或 `innerHTML`；日志列表使用 `slice(0,20)` 限制条目数。  
4. **资源加载**：样式与脚本通过 `<link>` / `<script>` 引入，避免阻塞渲染（可考虑延迟加载）。  

## 后端对接指南
1. **确保返回的 JSON 包含上述字段**（可省略默认值字段）。  
2. **建议接口路径**：`/api/skill/alpha-evol?symbol=600519`（返回单次分析结果）。  
3. **若需实时更新**：后端可通过 WebSocket 推送增量数据，前端调用 `window.updateAlphaEvol(partialData)`。  
4. **错误容忍**：前端会捕获异常并在控制台报错，界面会显示默认值或空值，不会因单个字段缺失而崩溃。  

## 使用示例
在任意页面中引入所需资源（已在基础模板中全局可用），然后：
```html
<div id="alpha-evol-container" class="mt-8"></div>

<script>
  // 假设通过 fetch 获得后端数据
  fetch('/api/skill/alpha-evol?symbol=600519')
    .then(r => r.json())
    .then(data => {
      // 初始化组件
      window.initAlphaEvol('#alpha-evol-container', data);
      // 后续若有更新：
      // window.updateAlphaEvol({level:4, exp:460, gain:120});
    })
    .catch(err => console.error('Alpha Evol load failed:', err));
</script>
```
> 示例代码已在 `alpha-evol.html` 底部的 `<script>` 块中给出，可直接复用。  

## 未来改进方向
- **虚拟形象动画**：引入 Lottie 或 Spine 实现更流畅的等级进化动画。  
- **互联雷达图**：增加 tooltip 显示具体分数及提升建议。  
- **K线真实集成**：统一使用项目现有的 K线图组件（如 `dashboard.js` 中的 `updateChart`），替换后备实现。  
- **主题切换**：支持用户自选暗色/亮色或其他科幻配方。  
- **国际化**：将中文标签抽离为 i18n 键，便于多语言支持。  

---  
*文档由 Kilo 自动生成，基于当前代码库状态。*  
*工作目录： /home/guxiao/projects/Skills Code/TradeMind*  
*当前时间： 2026-05-17T14:49:24+08:00*