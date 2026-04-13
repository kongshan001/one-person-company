#!/usr/bin/env python3
"""
IconForge Prompt 模板库
专业的游戏美术资产 Prompt 工程

每个模板包含：
- 结构化 prompt (主体/构图/风格/光影/排除词)
- 负面 prompt (避免常见生成问题)
- 风格一致性锚点 (同批次保持统一风格)
"""

from typing import Dict, List, Optional, Any

# ============ 专业 Prompt 结构 ============

PROMPT_STRUCTURE = {
    "subject": "主体描述 (物品/角色/场景)",
    "composition": "构图 (居中/特写/全景)",
    "style": "风格修饰词",
    "lighting": "光影效果",
    "detail": "细节增强",
    "negative": "排除词 (避免的问题)",
}

# 负面 prompt - 所有生成都应避免的常见问题
NEGATIVE_PROMPT = (
    "blurry, low quality, watermark, text, signature, "
    "cropped, out of frame, deformed, ugly, duplicate, "
    "morbid, mutilated, extra fingers, mutated hands, "
    "poorly drawn hands, poorly drawn face, mutation, "
    "bad anatomy, bad proportions, extra limbs, "
    "cloned face, disfigured, gross proportions, "
    "malformed limbs, missing arms, missing legs, "
    "extra arms, extra legs, fused fingers, too many fingers"
)

# 风格一致性锚点 - 同批次生成时追加到每张图，保持视觉统一
STYLE_ANCHORS = {
    "pixel": "consistent color palette, 16-color limit, no anti-aliasing, grid-aligned pixels",
    "cartoon": "consistent line weight 2px, same color saturation level, unified shading style",
    "realistic": "consistent render engine style, unified PBR material system, same ambient occlusion",
    "dark": "consistent dark palette, same desaturation level, unified rim lighting direction",
    "anime": "consistent cel-shading bands, same outline thickness, unified pastel tone mapping",
    "chinese": "consistent brush stroke style, same ink density, unified paper texture",
    "sci-fi": "consistent neon color temperature, same holographic overlay style, unified tech pattern",
}

# ============ 风格词库 (升级版) ============

STYLE_KEYWORDS_V2 = {
    "pixel": {
        "positive": "pixel art, retro game aesthetic, clean pixel edges, no anti-aliasing, 16-bit console style, limited color palette, sprite sheet ready",
        "lighting": "flat lighting, no gradients, hard edge shadows",
        "anchor": STYLE_ANCHORS["pixel"],
    },
    "cartoon": {
        "positive": "cartoon illustration, cute chibi style, bold black outlines 2px, flat cel shading, bright saturated colors, round friendly shapes",
        "lighting": "soft ambient light, minimal shadows, colorful highlights",
        "anchor": STYLE_ANCHORS["cartoon"],
    },
    "realistic": {
        "positive": "3D rendered, realistic PBR materials, detailed texture maps, volumetric lighting, physically based rendering, AAA game quality asset",
        "lighting": "dramatic rim lighting, ambient occlusion, subsurface scattering",
        "anchor": STYLE_ANCHORS["realistic"],
    },
    "dark": {
        "positive": "dark fantasy art, gothic aesthetic, weathered and worn textures, ominous ethereal glow, desaturated cold palette, bloodborne inspired",
        "lighting": "moonlight rim light, deep shadows, single point light source, volumetric fog",
        "anchor": STYLE_ANCHORS["dark"],
    },
    "anime": {
        "positive": "anime RPG illustration, cel-shaded, clean vector outlines, pastel color palette, kawaii proportions, gacha game style, studio art quality",
        "lighting": "soft diffused lighting, pastel rim highlights, minimal shadow bands",
        "anchor": STYLE_ANCHORS["anime"],
    },
    "chinese": {
        "positive": "Chinese ink painting style, watercolor wash, traditional xianxia aesthetic, elegant flowing brushstrokes, rice paper texture, donghua art",
        "lighting": "natural diffused light, ink gradient shading, soft ambient glow",
        "anchor": STYLE_ANCHORS["chinese"],
    },
    "sci-fi": {
        "positive": "sci-fi cyberpunk style, neon glow effects, holographic UI overlay, futuristic clean design, circuit pattern accents, chrome and glass materials",
        "lighting": "neon colored rim lights, holographic reflection, energy glow emission",
        "anchor": STYLE_ANCHORS["sci-fi"],
    },
}

# ============ 资产类型词库 (升级版) ============

TYPE_KEYWORDS_V2 = {
    "icon": {
        "positive": "game item icon, isolated on solid dark background, perfectly centered, square composition, single subject focus, clean silhouette",
        "detail": "high detail, sharp edges, readable at small size, iconic shape",
    },
    "sprite": {
        "positive": "character sprite, full body pose, transparent background, multiple animation frames, idle stance, clear silhouette, readable outline",
        "detail": "distinctive silhouette, clear color reading, animation ready",
    },
    "background": {
        "positive": "game background panorama, wide landscape, parallax layer ready, seamless edges, atmospheric depth, environmental storytelling",
        "detail": "rich detail, multiple depth layers, ambient atmosphere",
    },
    "tileset": {
        "positive": "seamless tileset, tiling game map element, grid-aligned, no visible seams, matching edge pixels, modular design",
        "detail": "tileable in all directions, consistent lighting, matching perspective",
    },
    "ui": {
        "positive": "game UI element, interface component, button frame panel, clean functional design, scalable vector style, consistent with game theme",
        "detail": "pixel-perfect edges, scalable, hover/active states implied",
    },
    "portrait": {
        "positive": "character portrait bust, head and shoulders, expressive face, detailed eyes, personality showing, dialogue ready, background blur",
        "detail": "expressive eyes, detailed hair, skin texture, emotional expression",
    },
    "card": {
        "positive": "card game art, card frame with illustration, CCG style, ornate border, mana cost area, stats display area, legendary rarity glow",
        "detail": "detailed illustration, card frame integration, rarity indicator",
    },
}

# ============ 批量预设方案 ============

PRESETS = {
    # RPG 基础道具包
    "rpg-weapons": {
        "name": "RPG 武器包",
        "description": "角色扮演游戏常见武器图标",
        "style": "dark",
        "asset_type": "icon",
        "count": 1,
        "prompts": [
            "iron longsword with leather wrapped handle",
            "wooden staff with glowing crystal orb on top",
            "ornate golden bow with enchanted string",
            "double-edged battle axe with runes carved in blade",
            "slim assassin dagger with poison drip",
            "massive war hammer with spiked head",
            "elegant rapier with jeweled basket hilt",
            "tribal spear with feather decorations",
            "crossbow with mechanical loading mechanism",
            "crescent moon scythe with ethereal glow",
            "pair of katars with flame engravings",
            "ancient spellbook with chained lock",
        ],
    },
    "rpg-potions": {
        "name": "RPG 药水包",
        "description": "各种药水和消耗品图标",
        "style": "cartoon",
        "asset_type": "icon",
        "count": 1,
        "prompts": [
            "red health potion in round glass bottle",
            "blue mana potion in tall flask",
            "green poison potion with skull cork",
            "golden elixir in ornate vial",
            "purple mystery potion bubbling",
            "white holy water in sacred vessel",
            "orange stamina potion with lightning mark",
            "pink love potion with heart shape",
            "black curse potion with dark smoke",
            "rainbow essence potion shimmering",
        ],
    },
    "rpg-armor": {
        "name": "RPG 防具包",
        "description": "盔甲和防具图标",
        "style": "realistic",
        "asset_type": "icon",
        "count": 1,
        "prompts": [
            "full plate armor helmet with visor",
            "leather chest armor with fur trim",
            "enchanted gauntlets with glowing runes",
            "dragon scale shield with emblem",
            "steel chainmail coif",
            "mystical robe with arcane symbols",
            "iron boots with spike cleats",
            "elven crown with gemstones",
            "shadow cloak with dark mist",
            "crystal ring with inner fire",
        ],
    },
    # 像素风游戏包
    "pixel-items": {
        "name": "像素风道具包",
        "description": "16-bit 像素风格游戏道具",
        "style": "pixel",
        "asset_type": "icon",
        "count": 1,
        "prompts": [
            "pixel art sword",
            "pixel art shield",
            "pixel art key",
            "pixel art gem",
            "pixel art coin",
            "pixel art heart container",
            "pixel art magic scroll",
            "pixel art food bread",
            "pixel art chest",
            "pixel art map",
        ],
    },
    # 修仙风道具包
    "xianxia-items": {
        "name": "修仙风道具包",
        "description": "仙侠/修仙风格道具图标",
        "style": "chinese",
        "asset_type": "icon",
        "count": 1,
        "prompts": [
            "jade talisman with floating inscriptions",
            "flying sword with spiritual aura",
            "gourd of spiritual wine with cloud patterns",
            "golden core pill emanating light",
            "lotus flower artifact with dew drops",
            "ancient bamboo scroll with calligraphy",
            "yin-yang jade pendant with swirling qi",
            "phoenix feather with flame trail",
            "dragon pearl with ocean mist",
            "mountain seal stamp with carved peaks",
        ],
    },
    # 卡牌游戏包
    "card-creatures": {
        "name": "卡牌生物包",
        "description": "卡牌游戏中的生物插画",
        "style": "anime",
        "asset_type": "card",
        "count": 1,
        "prompts": [
            "fire dragon breathing flames, fierce eyes, scaled wings spread",
            "forest elf ranger drawing bow in ancient woods",
            "undead knight in tattered armor, glowing blue eyes",
            "water elemental rising from ocean waves",
            "cute slime monster with happy expression, gelatinous body",
            "angel warrior with six wings and holy sword",
            "dark sorceress channeling shadow magic",
            "dwarven engineer with mechanical golem",
            "phoenix rebirthing from sacred ashes",
            "ancient treant guardian of the forest",
        ],
    },
    # 科幻风道具包
    "scifi-items": {
        "name": "科幻风道具包",
        "description": "赛博朋克/科幻风格道具图标",
        "style": "sci-fi",
        "asset_type": "icon",
        "count": 1,
        "prompts": [
            "plasma pistol with energy cell",
            "cybernetic implant chip with neural interface",
            "holographic data disk with encrypted code",
            "nano medkit with auto-injector",
            "gravity grenade with blue core",
            "EMP device with warning indicators",
            "quantum battery with glowing core",
            "stealth cloak module with active camo",
            "drone controller with holographic display",
            "alien artifact with unknown symbols",
        ],
    },
}


# ============ Prompt 构建器 ============

def build_pro_prompt(
    user_prompt: str,
    style: Optional[str] = None,
    asset_type: str = "icon",
    use_negative: bool = True,
    use_anchor: bool = True,
) -> Dict[str, Any]:
    """
    构建专业级文生图 prompt
    
    Args:
        user_prompt: 用户原始描述
        style: 风格名称（如 pixel, dark, cartoon 等）
        asset_type: 资产类型（如 icon, sprite, card 等）
        use_negative: 是否附加负面 prompt
        use_anchor: 是否附加风格一致性锚点
    
    Returns:
        {
            "prompt": "完整正面 prompt",
            "negative": "负面 prompt",
            "parts": {"subject": ..., "style": ..., ...}  # 用于调试
        }
    """
    parts = {}
    
    # 1. 主体
    parts["subject"] = user_prompt
    
    # 2. 资产类型词
    if asset_type in TYPE_KEYWORDS_V2:
        parts["type"] = TYPE_KEYWORDS_V2[asset_type]["positive"]
        parts["detail"] = TYPE_KEYWORDS_V2[asset_type]["detail"]
    
    # 3. 风格词
    if style and style in STYLE_KEYWORDS_V2:
        style_data = STYLE_KEYWORDS_V2[style]
        parts["style"] = style_data["positive"]
        parts["lighting"] = style_data["lighting"]
        if use_anchor:
            parts["anchor"] = style_data["anchor"]
    
    # 4. 组装 prompt
    prompt_parts = [v for v in parts.values() if v]
    full_prompt = ", ".join(prompt_parts)
    
    return {
        "prompt": full_prompt,
        "negative": NEGATIVE_PROMPT if use_negative else "",
        "parts": parts,
    }


def get_preset(preset_name: str) -> Dict[str, Any]:
    """获取预设方案
    
    Args:
        preset_name: 预设方案名称
    
    Returns:
        预设方案字典
    
    Raises:
        ValueError: 预设名称不存在时
    """
    if preset_name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise ValueError(f"预设 '{preset_name}' 不存在。可用: {available}")
    return PRESETS[preset_name]


def list_presets() -> List[Dict[str, Any]]:
    """列出所有可用预设
    
    Returns:
        预设摘要列表，每项包含 id, name, description, style, asset_type, item_count
    """
    result = []
    for key, preset in PRESETS.items():
        result.append({
            "id": key,
            "name": preset["name"],
            "description": preset["description"],
            "style": preset["style"],
            "asset_type": preset["asset_type"],
            "item_count": len(preset["prompts"]),
        })
    return result
