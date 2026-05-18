# Alpha Evol Skill - Hermes 使用教程

## 安装步骤

### 1. 下载 Skill 文件
```bash
# 在 Hermes 实例的 skills 目录下
cd /path/to/hermes/skills
wget https://raw.githubusercontent.com/fanjumin/TradeMind/main/skill_alpha_evol.py
```

### 2. 注册 Skill
在 Hermes 配置文件中添加：
```json
{
  "skills": [
    {
      "name": "alpha_evol",
      "path": "skills/skill_alpha_evol.py",
      "entry": "run"
    }
  ]
}
```

### 3. 重启 Hermes
```bash
systemctl restart hermes
# 或
pm2 restart hermes
```

## 使用方法

### 命令行调用
```bash
python skill_alpha_evol.py 600519
```

### HTTP API 调用
```
POST /api/skill/alpha_evol
Content-Type: application/json

{
  "symbol": "600519"
}

Response:
{
  "skill": "Alpha Evol",
  "level": 15,
  "exp": 2450,
  "exp_to_next": 3000,
  "this_gain": 180,
  "personality_message": "今天对宁德时代的技术形态分析让我有了新的突破！",
  "analysis": { ... },
  "radar_data": { ... },
  "evolution_log": [ ... ],
  "visual_suggestions": { ... }
}
```

### JavaScript 调用
```javascript
const response = await fetch('/api/skill/alpha_evol', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({symbol: '600519'})
});
const data = await response.json();
// data.radar_data -> ECharts 雷达图
// data.analysis -> 显示摘要
// data.visual_suggestions -> 头像等级、颜色主题
```

## 前端渲染指南

### 1. 引入必要资源
```html
<link rel="stylesheet" href="/static/css/tailwind.css">
<script src="/static/libs/echarts.min.js"></script>
```

### 2. 初始化组件
```javascript
// 使用 alpha-evol.html 中的 initAlphaEvol 函数
window.initAlphaEvol('#alpha-evol-root', data);
```

### 3. JSON 数据结构说明
| 字段 | 类型 | 说明 |
|------|------|------|
| skill | string | Skill 名称 |
| level | int | 当前等级 (1-100) |
| exp | int | 当前经验值 |
| exp_to_next | int | 升级所需经验 |
| this_gain | int | 本次获得经验 |
| personality_message | string | AI 个性化消息 |
| analysis | object | 分析结果 |
| radar_data | object | 5维能力分数 |
| evolution_log | array | 进化日志 |
| visual_suggestions | object | 视觉建议 |

## 常见问题

**Q: 如何重置等级？**
删除 `~/.hermes/skills/alpha_evol_state.json`（如果存在）

**Q: 如何修改经验公式？**
编辑 `_calculate_exp_gain()` 方法

**Q: 如何添加新能力维度？**
1. 在 `__init__` 中添加新键
2. 在 `_update_abilities` 中处理
3. 在前端雷达图配置中增加轴