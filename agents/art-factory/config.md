# 🎨 美术工厂 Agent 配置

name: art-factory
version: 1.0.0
description: 批量生成游戏美术资产的 AI Agent

## 触发条件

- "生成图标" / "generate icon"
- "美术资产" / "game asset"
- "道具图标" / "item icon"
- "角色立绘" / "character sprite"
- "场景背景" / "scene background"

## 生成流水线

### Step 1: 需求解析
```
输入: 用户描述（自然语言）
输出: 结构化需求
  - 风格: pixel / cartoon / realistic / dark / anime / chinese
  - 类型: icon / sprite / background / tileset / ui
  - 数量: 1-100
  - 尺寸: 64 / 128 / 256 / 512
  - 主题: 酒桶 / 剑 / 盾牌 / ...
```

### Step 2: Prompt 生成
```
模板: "[style_keywords] [subject], [type_keywords], [detail_keywords], [background], [size_hint]"

示例:
  用户说: "暗黑风的酒桶图标"
  生成 prompt: "dark fantasy game item icon, wooden barrel with iron bands, weathered wood texture, ominous glow, desaturated colors, dramatic lighting, isolated on dark background, 512x512"
```

### Step 3: 批量生成
```
API: Pollinations.ai (免费) / Flux via Replicate (付费)
参数:
  - width: 512
  - height: 512
  - seed: random (确保多样性)
  - nologo: true
  - 每张间隔 2-3 秒 (避免限流)
```

### Step 4: 后处理
```
1. 格式转换: JPEG → PNG (ImageMagick)
2. 尺寸裁剪: 512 → 64/128/256 (ImageMagick resize)
3. 去背景: rembg (需要 pip, 后期加)
4. 命名: {style}_{subject}_{size}.png
```

### Step 5: 质检
```
规则:
  - 文件大小 > 5KB (排除空白/损坏)
  - 分辨率正确
  - 感知哈希去重 (相似度 < 90%)
  - 每 10 张抽检 1 张 (人工)
  - 不合格率 > 30% → 整批重新生成
```

### Step 6: 打包交付
```
输出:
  - ZIP: {project_name}_assets.zip
  - 预览页: index.html (缩略图网格)
  - 清单: manifest.json (文件列表 + prompt)
```

## 风格关键词库

| 风格 | 关键词 |
|------|--------|
| pixel | `pixel art, retro, 32x32 sprite, clean edges, game boy style` |
| cartoon | `cartoon, cute, bold outlines, flat shading, bright colors, chibi` |
| realistic | `3D rendered, realistic, detailed texture, dramatic lighting, PBR` |
| dark | `dark fantasy, gothic, weathered, ominous glow, desaturated, bloodborne style` |
| anime | `anime RPG, cel shading, pastel, kawaii, clean vector, gacha style` |
| chinese | `Chinese ink painting, watercolor, traditional, elegant, xianxia` |
| sci-fi | `sci-fi, cyberpunk, neon glow, holographic, futuristic, clean design` |
