# ── Vivid Layout Generator — Python/FastAPI + Groq version ────────
# pip install fastapi uvicorn httpx oracledb python-multipart pillow colorthief
# Run: uvicorn server:app --port 8000 --reload

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from colorthief import ColorThief
from PIL import Image
from dotenv import load_dotenv
import base64, io, os, json, httpx, asyncio, time, re, copy

load_dotenv()  # Load .env file

app = FastAPI(title="Vivid Layout Generator — Groq/Python")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Config ─────────────────────────────────────────────────────────
OUTPUT_DIR    = Path(os.getcwd())
CLAUDE_GROQ   = OUTPUT_DIR / "CLAUDE_GROQ.md"
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION   = os.getenv("GROQ_VISION", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"
FIGMA_TOKEN   = os.getenv("FIGMA_TOKEN", "")
FIGMA_MCP_URL = "https://mcp.figma.com/mcp"

# ── Hermes (Ollama) Config ─────────────────────────────────────────
HERMES_ENABLED = os.getenv("HERMES_ENABLED", "true").lower() == "true"
HERMES_MODEL   = os.getenv("HERMES_MODEL", "nous-hermes2")
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
LEARNED_RULES  = OUTPUT_DIR / "hermes_rules.json"

# ── Hermes Helper Functions ────────────────────────────────────────
def load_learned_rules() -> list:
    try:
        if LEARNED_RULES.exists():
            data = json.loads(LEARNED_RULES.read_text(encoding="utf-8"))
            return data.get("rules", [])
    except Exception:
        pass
    return []

def save_learned_rules(rules: list):
    try:
        existing = load_learned_rules()
        merged = list(dict.fromkeys(rules + existing))[:30]
        LEARNED_RULES.write_text(
            json.dumps({"rules": merged, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2),
            encoding="utf-8"
        )
        print(f"[hermes] saved {len(merged)} learned rules")
    except Exception as e:
        print(f"[hermes] failed to save rules: {e}")

async def call_hermes(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(OLLAMA_URL, json={
                "model":   HERMES_MODEL,
                "prompt":  prompt,
                "stream":  False,
                "options": {"temperature": 0.1, "num_predict": 2000}
            })
            response = r.json().get("response", "").strip()
            print(f"[hermes] response len={len(response)}")
            return response
    except Exception as e:
        print(f"[hermes] unavailable: {e}")
        return ""

async def hermes_validate(layout_json: dict) -> dict:
    if not HERMES_ENABLED:
        return {"valid": True, "issues": [], "score": 100}
    sample = json.dumps({"control": layout_json.get("control", [])[:3]}, indent=2)[:3000]
    prompt = f"""You are a Vivid Layout JSON validator for BusinessNext designer.

Review this JSON and find issues that cause designer CRASHES when clicking widgets.

KNOWN CRASH CAUSES:
1. Vivid_Label missing: textstyle object, tooltipMsg, showTooltip, isMasking, maskLength, maskPosition, maskCharacter
2. Vivid_Button missing: hideShadow, disableRipple, buttonHoverColor, buttonBgHoverColor, targetMode, targetUrl, subpath
3. Vivid_Image missing: Source (capital S), Base64, alt, icon properties
4. Container (1005) missing: collapse_expand, containerCollapseIcon, containerExpandIcon, containerIconHeight, containerIconWidth
5. visibility not string "true true true"
6. textstyle not object with Bold/Italic/Underlined/Strikeout keys
7. isfield not boolean

JSON:
{sample}

Respond ONLY with JSON:
{{"valid": true, "score": 0-100, "issues": ["issue1"], "missing_props": {{"widget_type": ["prop1"]}}}}"""

    raw = await call_hermes(prompt)
    if not raw:
        return {"valid": True, "issues": [], "score": 100}
    try:
        f, l = raw.find('{'), raw.rfind('}')
        if f != -1 and l != -1:
            result = json.loads(raw[f:l+1])
            print(f"[hermes-validate] score={result.get('score')} issues={len(result.get('issues', []))}")
            return result
    except Exception as e:
        print(f"[hermes-validate] parse failed: {e}")
    return {"valid": True, "issues": [], "score": 100}

async def hermes_review_and_learn(layout_json: dict, issue_description: str = "") -> list:
    if not HERMES_ENABLED:
        return []
    sample_str = json.dumps(layout_json, indent=2)[:2000]
    prompt = f"""You are a Vivid Layout expert reviewing a bad AI-generated layout JSON.

PROBLEM: {issue_description or "Designer crashes when clicking widgets"}

BAD JSON SAMPLE:
{sample_str}

Extract SPECIFIC fix rules to prevent this mistake in future generations.
Rules must be short, actionable, specific to Vivid JSON schema.

Respond ONLY with JSON:
{{"rules": ["ALWAYS include textstyle object...", "NEVER set visibility to boolean..."], "root_cause": "one sentence"}}"""

    raw = await call_hermes(prompt)
    if not raw:
        return []
    try:
        f, l = raw.find('{'), raw.rfind('}')
        if f != -1 and l != -1:
            result = json.loads(raw[f:l+1])
            new_rules = result.get("rules", [])
            print(f"[hermes-review] root_cause: {result.get('root_cause','')}")
            print(f"[hermes-review] learned {len(new_rules)} new rules")
            if new_rules:
                save_learned_rules(new_rules)
            return new_rules
    except Exception as e:
        print(f"[hermes-review] parse failed: {e}")
    return []

def inject_learned_rules(prompt: str) -> str:
    rules = load_learned_rules()
    if not rules:
        return prompt
    rules_text = "\n".join(f"- {r}" for r in rules[:15])
    injection = f"\n\nLEARNED FIX RULES (from past failures — follow strictly):\n{rules_text}\n"
    if "<context>" in prompt:
        return prompt.replace("</context>", f"</context>{injection}", 1)
    return injection + prompt


def get_schema() -> str:
    try: return CLAUDE_GROQ.read_text(encoding="utf-8")
    except: return ""

# ── Figma MCP ───────────────────────────────────────────────────────
async def get_figma_design_via_mcp(figma_url: str) -> dict:
    """
    Call Figma MCP server via HTTP.
    Returns exact design data — colors, layout, components.
    200 calls/day on Professional plan.
    """
    file_match = re.search(r'figma\.com/(?:file|design)/([a-zA-Z0-9]+)', figma_url)
    node_match = re.search(r'node-id=([^&]+)', figma_url)
    if not file_match:
        raise Exception("Invalid Figma URL")
    file_key = file_match.group(1)
    node_id  = node_match.group(1).replace('-', ':') if node_match else None
    print(f"[figma-mcp] fileKey={file_key} nodeId={node_id}")

    async with httpx.AsyncClient(timeout=30) as client:
        # Use Figma REST API /v1/files/ — works with personal access token
        # MCP remote server requires OAuth (not PAT)
        params = {"depth": "5"}
        if node_id:
            params["ids"] = node_id

        url = f"https://api.figma.com/v1/files/{file_key}/nodes" if node_id else f"https://api.figma.com/v1/files/{file_key}"
        r = await client.get(
            url,
            headers={"X-Figma-Token": FIGMA_TOKEN},
            params=params
        )
        data = r.json()
        if "err" in data or "status" in data:
            raise Exception(f"Figma REST API error: {data.get('err') or data.get('status')}")
        print(f"[figma-mcp] REST API success, keys: {list(data.keys())}")
        return data

def rgba_to_hex(r: float, g: float, b: float) -> str:
    return '#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b*255))

def extract_colors_from_mcp(mcp_data: dict) -> dict:
    """
    Extract exact hex colors from Figma MCP response.
    Handles both node tree format and get_design_context text format.
    """
    colors = {
        "dominant_colors_hex": [],
        "button_colors":       [],
        "panel_colors":        [],
        "background_color":    "#ffffff",
        "text_colors":         []
    }
    seen = set()

    def add_color(hex_c):
        if hex_c and hex_c not in seen and len(hex_c) in (4, 7):
            seen.add(hex_c)
            colors["dominant_colors_hex"].append(hex_c)

    def traverse(node, depth=0):
        if not node or depth > 12: return
        node_type = node.get('type', '')
        # Fill colors
        for fill in node.get('fills', []):
            if fill.get('type') == 'SOLID' and fill.get('visible', True):
                c = fill.get('color', {})
                if c:
                    hex_c = rgba_to_hex(c.get('r',0), c.get('g',0), c.get('b',0))
                    add_color(hex_c)
                    if node_type in ('FRAME','RECTANGLE','COMPONENT','INSTANCE'):
                        colors['panel_colors'].append({"position": node.get('name',''), "background": hex_c})
        # Text colors
        if node_type == 'TEXT':
            for fill in node.get('fills', []):
                if fill.get('type') == 'SOLID':
                    c = fill.get('color', {})
                    if c:
                        hex_c = rgba_to_hex(c.get('r',0), c.get('g',0), c.get('b',0))
                        add_color(hex_c)
                        colors['text_colors'].append(hex_c)
        # Stroke colors
        for stroke in node.get('strokes', []):
            if stroke.get('type') == 'SOLID':
                c = stroke.get('color', {})
                if c:
                    add_color(rgba_to_hex(c.get('r',0), c.get('g',0), c.get('b',0)))
        for child in node.get('children', []):
            traverse(child, depth+1)

    result = mcp_data.get('result', {})

    # Handle Figma REST API /v1/files/nodes response
    nodes = mcp_data.get('nodes', {})  # from /v1/files/{key}/nodes
    document = mcp_data.get('document', {})  # from /v1/files/{key}

    if nodes:
        for node_wrapper in nodes.values():
            doc = node_wrapper.get('document', {})
            traverse(doc)
    elif document:
        traverse(document)

    # Handle text content from MCP get_design_context (fallback)
    content = result.get('content', [])
    if content and not colors['dominant_colors_hex']:
        for block in content:
            text = block.get('text', '') if isinstance(block, dict) else str(block)
            hex_colors = re.findall(r'#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}', text)
            for hex_c in hex_colors:
                add_color(hex_c.lower())

    # Set background from most common color or first color
    if colors['dominant_colors_hex']:
        colors['background_color'] = colors['dominant_colors_hex'][0]

    colors['dominant_colors_hex'] = list(dict.fromkeys(colors['dominant_colors_hex']))[:10]
    colors['text_colors']         = list(dict.fromkeys(colors['text_colors']))[:4]
    print(f"[figma-mcp] extracted {len(colors['dominant_colors_hex'])} colors: {colors['dominant_colors_hex'][:6]}")
    return colors

async def get_figma_screenshot(figma_url: str) -> tuple[str, str]:
    """
    Get rendered screenshot of Figma frame via REST API.
    Used as fallback for vision layout detection.
    Returns (base64_image, image_type)
    """
    file_match = re.search(r'figma\.com/(?:file|design)/([a-zA-Z0-9]+)', figma_url)
    node_match = re.search(r'node-id=([^&]+)', figma_url)
    if not file_match: raise Exception("Invalid Figma URL")
    file_key = file_match.group(1)
    node_id  = node_match.group(1).replace('-', ':') if node_match else None

    async with httpx.AsyncClient(timeout=30) as client:
        params = {"format": "png", "scale": "1"}
        if node_id: params["ids"] = node_id
        r = await client.get(
            f"https://api.figma.com/v1/images/{file_key}",
            headers={"X-Figma-Token": FIGMA_TOKEN},
            params=params
        )
        data = r.json()
        images = data.get('images', {})
        if not images: raise Exception("No images returned from Figma")
        img_url = list(images.values())[0]

        # Download the image
        img_r = await client.get(img_url)
        b64   = base64.b64encode(img_r.content).decode('utf-8')
        return b64, "image/png"
def extract_dominant_colors(base64_image: str, top_n: int = 10) -> list[str]:
    """Extract exact hex colors from image pixels — no guessing."""
    try:
        buffer = base64.b64decode(base64_image)

        # ColorThief for dominant palette
        ct = ColorThief(io.BytesIO(buffer))
        palette = ct.get_palette(color_count=top_n, quality=1)
        ct_colors = ['#{:02x}{:02x}{:02x}'.format(r, g, b) for r, g, b in palette]

        # Pillow grid sampling for edge/accent colors ColorThief might miss
        img = Image.open(io.BytesIO(buffer)).convert('RGB').resize((200, 200))
        w, h = img.size
        grid = 10
        grid_colors: dict[str, int] = {}
        for gy in range(grid):
            for gx in range(grid):
                px = int((gx / grid) * w)
                py = int((gy / grid) * h)
                r, g, b = img.getpixel((px, py))
                # Quantize to nearest 8 for deduplication
                rq = round(r / 8) * 8
                gq = round(g / 8) * 8
                bq = round(b / 8) * 8
                hex_c = '#{:02x}{:02x}{:02x}'.format(
                    min(rq, 255), min(gq, 255), min(bq, 255))
                grid_colors[hex_c] = grid_colors.get(hex_c, 0) + 1

        grid_top = [h for h, _ in sorted(
            grid_colors.items(), key=lambda x: x[1], reverse=True)][:top_n]

        # Merge both lists, deduplicate, keep top_n
        merged = list(dict.fromkeys(ct_colors + grid_top))[:top_n]
        print(f"[colors] extracted: {merged}")
        return merged

    except Exception as e:
        print(f"[colors] error: {e}")
        return []

# ── postProcess — same logic as server_groq.js ─────────────────────
def fix_ids(obj, seen: set = None, counter: list = None):
    if seen is None: seen = set()
    if counter is None: counter = [0]
    if not obj or not isinstance(obj, (dict, list)):
        return obj
    if isinstance(obj, list):
        for item in obj: fix_ids(item, seen, counter)
        return obj

    # Fix Vivid_Container → Container
    if obj.get('type') == 'Vivid_Container':
        obj['type'] = 'Container'

    # Fix source/src → Source for Vivid_Image
    if obj.get('type') == 'Vivid_Image' or obj.get('controlType') == 'Vivid_Image':
        for p in obj.get('property', []):
            if p.get('name') in ('source', 'src'):
                p['name'] = 'Source'

    obj_id = obj.get('id', '')
    placeholder_ids = {
        'id_X', 'id_XXXXXXXXXXXXXXXXXX', 'id_<18digits>', 'id_<18>',
        'c_XXXXXXXXXXXXX', 'c_section_XXXXXX', 'c_<13digits>',
        'c_<id>', 'c_111111111111'
    }
    is_placeholder = (
        obj_id in placeholder_ids or
        obj_id in seen or
        re.match(r'^id_\d+$', obj_id) or
        re.match(r'^c_\d+$', obj_id)
    )
    if obj_id and is_placeholder:
        counter[0] += 1
        ts = str(int(time.time() * 1000))[-8:]
        n = str(counter[0]).zfill(6)
        ct = obj.get('controlType', '')
        t = obj.get('type', '')
        if ct == '999' or t == 'Section':
            obj['id'] = f'c_section_{ts}{n}'
        elif ct == '1005' or t == 'Container':
            obj['id'] = f'c_{ts}{n}{ts}'
        else:
            obj['id'] = f'id_{ts}{n}{ts}{n}'
    if obj.get('id'):
        seen.add(obj['id'])

    for v in obj.values():
        if isinstance(v, (dict, list)):
            fix_ids(v, seen, counter)
    return obj

def ensure_property(props: list, name: str, value, extra: dict = None):
    """Add a property if it doesn't exist, or fix it if value is wrong."""
    for p in props:
        if p.get('name') == name:
            return  # already exists
    entry = {'name': name, 'value': value}
    if extra:
        entry.update(extra)
    props.append(entry)

def sanitize_properties(obj):
    if not obj or not isinstance(obj, (dict, list)):
        return obj
    if isinstance(obj, list):
        for item in obj: sanitize_properties(item)
        return obj

    ctrl_type = obj.get('controlType', '') or obj.get('type', '')
    props = obj.get('property', [])

    # Fix existing property values
    for p in props:
        name = p.get('name', '')
        val  = p.get('value')

        # Fix None values
        if val is None:
            if name == 'visibility':                    p['value'] = 'true true true'
            elif name == 'flexColumn':                  p['value'] = True
            elif name == 'wrap':                        p['value'] = False
            elif name in ('fullWidth', 'fullHeight'):   p['value'] = False
            elif name in ('isfield', 'required', 'readOnly'): p['value'] = False
            else:                                       p['value'] = ''

        # visibility must always be string "true true true"
        if name == 'visibility' and not isinstance(val, str):
            p['value'] = 'true true true'

        # textstyle must always be full object
        if name == 'textstyle':
            if not isinstance(val, dict):
                p['value'] = {'Bold': False, 'Italic': False, 'Underlined': False, 'Strikeout': False}
            else:
                p['value'] = {
                    'Bold':       bool(val.get('Bold', False)),
                    'Italic':     bool(val.get('Italic', False)),
                    'Underlined': bool(val.get('Underlined', False)),
                    'Strikeout':  bool(val.get('Strikeout', False)),
                }

        # All string properties must be strings, not None
        if name in ('backgroundColor', 'color', 'borderColor', 'borderRadius',
                    'borderWidth', 'borderStyle', 'fontSize', 'gap', 'className',
                    'minHeight', 'width', 'align', 'justify') and val is None:
            p['value'] = ''

    # Ensure critical properties EXIST (missing = crash in designer)
    if props is not None:
        # visibility is required on ALL nodes
        ensure_property(props, 'visibility', 'true true true')

        # Label must have textstyle
        if ctrl_type in ('Vivid_Label',):
            ensure_property(props, 'textstyle',
                {'Bold': False, 'Italic': False, 'Underlined': False, 'Strikeout': False},
                {'type': 'textstyle'})
            ensure_property(props, 'color', '#333333')
            ensure_property(props, 'fontSize', '14px')
            ensure_property(props, 'backgroundColor', 'transparent')

        # Button must have these
        if ctrl_type in ('Vivid_Button',):
            ensure_property(props, 'backgroundColor', '#003874')
            ensure_property(props, 'color', '#ffffff')
            ensure_property(props, 'borderRadius', '4px')
            ensure_property(props, 'borderWidth', '')
            ensure_property(props, 'borderColor', '')
            ensure_property(props, 'borderStyle', '')
            ensure_property(props, 'fullWidth', False)
            ensure_property(props, 'fontSize', '14px')

        # TextBox must have these
        if ctrl_type in ('Vivid_TextBox',):
            ensure_property(props, 'placeholder', '')
            ensure_property(props, 'value', '')
            ensure_property(props, 'fullWidth', True)
            ensure_property(props, 'isfield', True)
            ensure_property(props, 'required', False)
            ensure_property(props, 'readOnly', False)
            ensure_property(props, 'backgroundColor', '#ffffff')
            ensure_property(props, 'color', '#333333')

        # Container must have flexColumn and wrap
        if ctrl_type in ('1005', 'Container', 'vivid_GridContainer'):
            ensure_property(props, 'flexColumn', True)
            ensure_property(props, 'wrap', True)
            ensure_property(props, 'col', 12)
            ensure_property(props, 'lg', '12')
            ensure_property(props, 'md', '12')

        # Image must have Source (capital S)
        if ctrl_type in ('Vivid_Image',):
            # Fix src/source → Source
            for p in props:
                if p.get('name') in ('src', 'source'):
                    p['name'] = 'Source'
            ensure_property(props, 'Source', '')
            ensure_property(props, 'width', '100%')
            ensure_property(props, 'height', 'auto')

    for v in obj.values():
        if isinstance(v, (dict, list)):
            sanitize_properties(v)
    return obj

def post_process(data: dict) -> dict:
    if not data: return data
    fix_ids(data)
    sanitize_properties(data)
    return data

# ── Groq API calls ─────────────────────────────────────────────────
async def call_groq_text(prompt: str, max_tokens: int = 8000) -> str:
    use_model = GROQ_MODEL
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": use_model, "max_tokens": max_tokens,
                  "temperature": 0.1,
                  "messages": [{"role": "user", "content": prompt}]}
        )
        data = r.json()
        if "error" in data:
            raise Exception(data["error"]["message"])
        text = data["choices"][0]["message"]["content"]
        print(f"[groq-text] tokens={data.get('usage',{}).get('total_tokens')} len={len(text)}")
        return text

async def call_groq_vision(base64_image: str, image_type: str, prompt: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": GROQ_VISION, "max_tokens": 4000, "temperature": 0.1,
                  "messages": [{"role": "user", "content": [
                      {"type": "image_url",
                       "image_url": {"url": f"data:{image_type};base64,{base64_image}"}},
                      {"type": "text", "text": prompt}
                  ]}]}
        )
        data = r.json()
        if "error" in data:
            raise Exception(data["error"]["message"])
        text = data["choices"][0]["message"]["content"]
        print(f"[groq-vision] len={len(text)}")
        return text

# ── Stage 1A: Dedicated Color Extraction Vision Call ──────────────
# Inspired by Vision-to-JSON technique (Medium/Coding Nexus):
# Separate focused call for colors only → forensic precision
async def extract_colors_via_vision(base64_image: str, image_type: str) -> dict:
    """Dedicated vision call focused ONLY on color extraction."""
    color_prompt = """You are a forensic UI color analyst. Extract EXACT hex colors from this UI screenshot.
Output ONLY this JSON. No explanation. Start with {:
{
  "dominant_colors_hex": ["#hex1", "#hex2", "#hex3", "#hex4", "#hex5", "#hex6"],
  "accent_colors_hex": ["#hex1", "#hex2"],
  "background_color": "#hex",
  "text_colors": ["#hex1", "#hex2"],
  "button_colors": [
    {"text": "exact button label", "background": "#hex", "text_color": "#hex", "border": "#hex or none"}
  ],
  "panel_colors": [
    {"position": "left OR right OR full OR top OR bottom", "background": "#hex"}
  ],
  "shape_colors": [
    {"shape": "wave OR blob OR circle OR diagonal OR card OR strip", "color": "#hex", "position": "top OR bottom OR left OR right OR background"}
  ]
}
RULES:
- Forensic precision — read actual pixel colors, never approximate
- Every button must have its own entry in button_colors
- dominant_colors_hex = top 6 most used colors in the UI
- shape_colors = ALL decorative shapes (waves, blobs, circles, diagonals, cards)
- Never ignore a shape — capture its color in shape_colors
- Output JSON only, start with {"""

    try:
        raw = await call_groq_vision(base64_image, image_type, color_prompt)
        raw = raw.strip()
        raw = re.sub(r'^```json\s*', '', raw, flags=re.IGNORECASE)
        raw = re.sub(r'^```\s*', '', raw, flags=re.IGNORECASE)
        raw = re.sub(r'```\s*$', '', raw)
        f, l = raw.find('{'), raw.rfind('}')
        if f != -1 and l != -1:
            raw = raw[f:l+1]
        color_data = json.loads(raw)
        print(f"[vision-colors] extracted: {color_data.get('dominant_colors_hex', [])}")
        return color_data
    except Exception as e:
        print(f"[vision-colors] failed: {e}")
        return {}

def merge_color_sources(vision_colors: dict, pixel_colors: list) -> dict:
    """
    Merge vision-extracted colors with Pillow/ColorThief pixel colors.
    Vision colors take priority (more accurate for UI elements).
    Pixel colors fill gaps.
    """
    dominant = vision_colors.get("dominant_colors_hex", [])
    accent   = vision_colors.get("accent_colors_hex", [])
    all_vision = dominant + accent

    # Use pixel colors to validate/supplement — add any not already in vision list
    supplementary = [c for c in pixel_colors if c not in all_vision][:4]
    final_palette  = list(dict.fromkeys(all_vision + supplementary))  # deduplicate

    print(f"[colors-merged] final palette: {final_palette[:8]}")
    return {
        "palette":       final_palette[:8],
        "background":    vision_colors.get("background_color", "#ffffff"),
        "button_colors": vision_colors.get("button_colors", []),
        "panel_colors":  vision_colors.get("panel_colors", []),
        "text_colors":   vision_colors.get("text_colors", []),
        "shape_colors":  vision_colors.get("shape_colors", []),
    }

# ── Stage 1B: Layout/Structure Vision Call ─────────────────────────
async def extract_layout_via_vision(base64_image: str, image_type: str, merged_colors: dict) -> str:
    """Layout detection call — uses merged color palette for accuracy."""

    # Build color context from merged sources
    palette_str = ", ".join(merged_colors.get("palette", []))

    # Build button color lookup string
    btn_lookup = ""
    for btn in merged_colors.get("button_colors", []):
        btn_lookup += f'\n  - Button "{btn.get("text","")}" → bg:{btn.get("background","?")} color:{btn.get("text_color","?")} border:{btn.get("border","none")}'

    # Build panel color lookup string
    panel_lookup = ""
    for panel in merged_colors.get("panel_colors", []):
        panel_lookup += f'\n  - {panel.get("position","?")} panel → bg:{panel.get("background","?")}'

    # Build shape color lookup string
    shape_lookup = ""
    for shape in merged_colors.get("shape_colors", []):
        shape_lookup += f'\n  - {shape.get("shape","?")} at {shape.get("position","?")} → color:{shape.get("color","?")}'

    color_context = f"""
VERIFIED COLOR PALETTE (use ONLY these hex values):
All colors: {palette_str}
Background: {merged_colors.get("background", "#ffffff")}
Text colors: {", ".join(merged_colors.get("text_colors", []))}
Button colors:{btn_lookup if btn_lookup else " (use palette above)"}
Panel colors:{panel_lookup if panel_lookup else " (use palette above)"}
Decorative shapes:{shape_lookup if shape_lookup else " none detected"}

For each element, pick its color from the verified palette above. Do NOT invent new colors."""

    prompt = f"""STEP 1 - DETECT LAYOUT DIRECTION:
Scan the image LEFT TO RIGHT. Are there two or more panels SIDE BY SIDE horizontally?
- YES → layout = "two-column"
- NO  → layout = "single-column"
NEVER call a side-by-side layout single-column.

STEP 2 - OUTPUT this exact JSON only. No explanation, no markdown, start with {{:
{{
  "pageBackground": "#hex",
  "layout": "two-column OR single-column OR three-column",
  "columns": [
    {{
      "position": "left OR full OR right",
      "widthPercent": 50,
      "background": "#hex",
      "elements": [
        {{
          "type": "Label OR Button OR TextBox OR Image OR Icon OR Divider",
          "text": "EXACT visible text",
          "color": "#hex — extract exact color per element",
          "fontSize": "12px|14px|16px|20px|24px|32px",
          "bold": false,
          "fullWidth": false,
          "style": "filled OR outlined OR pill OR circle OR text",
          "backgroundColor": "#hex or transparent",
          "borderColor": "#hex or null",
          "borderRadius": "4px",
          "borderWidth": "1px or null",
          "placeholder": "for TextBox only"
        }}
      ]
    }}
  ]
}}

CRITICAL RULES:
- Output JSON only, start with {{
- style=filled → solid colored background button
- style=outlined → transparent bg, colored border
- style=pill → filled with borderRadius 20px+
- style=circle → small round social icon button
- Copy ALL text EXACTLY as shown
- Two panels side by side = ALWAYS two-column
- EVERY Label gets its OWN color extracted from the image — never use #333 as default
- Subtitle/description text → extract exact color (may be red, gray, coral etc.)
- TextBox → add borderColor (exact border color), borderRadius (4px if slightly rounded)
- Logo/brand image → type:Image NOT type:Icon
- Illustration/drawing → type:Image NOT type:Icon
- Decorative wave/blob/curved shape → capture as column background color
- If page has wave background → set that column background to the wave color
- SHAPE HANDLING — map ALL decorative shapes to container backgrounds:
  * Wave/curved panel → Container backgroundColor (use the shape's color)
  * Diagonal split → two columns with different backgroundColor
  * Circle/oval accent → note as Container with borderRadius:50% backgroundColor
  * Rounded card → Container backgroundColor with borderRadius
  * Bottom color band → separate Container with that backgroundColor
  * Gradient → use dominant color as backgroundColor
  * NEVER ignore any shape — always capture its color as a container background
{color_context}"""

    raw = await call_groq_vision(base64_image, image_type, prompt)
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'^```\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'```\s*$', '', raw)
    f, l = raw.find('{'), raw.rfind('}')
    if f != -1 and l != -1:
        raw = raw[f:l+1]
    print(f"[vision-layout] raw: {raw[:200]}")
    return raw

# ── Stage 1: Orchestrate all vision calls ─────────────────────────
async def analyze_image_structured(base64_image: str, image_type: str) -> str:
    """
    Two-call vision pipeline inspired by Vision-to-JSON technique:
    Call 1 → dedicated color extraction (forensic precision)
    Call 2 → layout/structure detection (uses verified colors)
    + Pillow/ColorThief pixel sampling as validation layer
    """
    # Run pixel color extraction and vision color call in parallel
    pixel_task  = asyncio.to_thread(extract_dominant_colors, base64_image)
    vision_task = extract_colors_via_vision(base64_image, image_type)

    pixel_colors, vision_colors = await asyncio.gather(pixel_task, vision_task)

    # Merge both color sources
    merged_colors = merge_color_sources(vision_colors, pixel_colors)

    # Layout detection with verified color context
    layout_raw = await extract_layout_via_vision(base64_image, image_type, merged_colors)

    return layout_raw

# ── Stage 2a: Structured JSON → Vivid JSON ────────────────────────
async def generate_from_structured(structured: str, extra_prompt: str = "") -> dict:
    schema = get_schema()

    # Parse vision JSON → explicit line-by-line summary
    analysis_text = structured
    try:
        parsed = json.loads(structured)
        layout = parsed.get('layout', 'single-column')
        page_bg = parsed.get('pageBackground', '#ffffff')
        columns = parsed.get('columns', [])

        lines = [
            f"LAYOUT_TYPE: {layout}",
            f"PAGE_BACKGROUND: {page_bg}",
            f"COLUMN_COUNT: {len(columns)}",
            ""
        ]
        for i, col in enumerate(columns):
            lines.append(f"--- COLUMN_{i+1} [width:{col.get('widthPercent',50)}%, background:{col.get('background','transparent')}] ---")
            for el in col.get('elements', []):
                t = el.get('type', '')
                if t == 'Label':
                    lines.append(f"  Label: \"{el.get('text','')}\" fontSize:{el.get('fontSize','14px')} bold:{el.get('bold',False)} color:{el.get('color','#333333')}")
                elif t == 'Button':
                    bg = el.get('backgroundColor') or el.get('background') or '#003874'
                    lines.append(f"  Button: \"{el.get('text','')}\" style:{el.get('style','filled')} backgroundColor:{bg} color:{el.get('color','#ffffff')} borderColor:{el.get('borderColor','')} borderRadius:{el.get('borderRadius','4px')} fullWidth:{el.get('fullWidth',False)}")
                elif t == 'TextBox':
                    lines.append(f"  TextBox placeholder:\"{el.get('placeholder') or el.get('text','Enter')}\" borderColor:{el.get('borderColor','#e0e0e0')} borderRadius:{el.get('borderRadius','4px')} borderWidth:{el.get('borderWidth','1px')}")
                elif t == 'Divider':
                    lines.append("  Divider")
                elif t == 'Image':
                    lines.append(f"  Image width:{el.get('width','100%')}")
                elif t == 'Icon':
                    lines.append(f"  Icon name:\"{el.get('icon','HomeRounded')}\" color:{el.get('color','#333333')}")
            lines.append("")
        analysis_text = "\n".join(lines)
    except Exception:
        pass  # use raw string if JSON parse fails

    # Fix 4 — Dynamic max_tokens based on layout complexity
    # Count elements from BOTH the analysis_text AND original columns (fixes elements=1 bug)
    element_count = (
        analysis_text.count("Label:") +
        analysis_text.count("Button:") +
        analysis_text.count("TextBox:") +
        analysis_text.count("Image") +
        analysis_text.count("Icon:") +
        analysis_text.count("Divider")
    )
    # Also count from original structured JSON columns if available
    try:
        parsed_check = json.loads(structured)
        col_element_count = sum(
            len(col.get('elements', [])) for col in parsed_check.get('columns', [])
        )
        element_count = max(element_count, col_element_count)
    except Exception:
        pass

    # Minimum 5000 tokens — even 1 element generates a large Vivid JSON
    if element_count <= 3:
        max_tokens = 5000
    elif element_count <= 6:
        max_tokens = 6000
    elif element_count <= 10:
        max_tokens = 7000
    elif element_count <= 14:
        max_tokens = 8000
    else:
        max_tokens = 8192  # Groq hard max
    print(f"[groq] elements={element_count} max_tokens={max_tokens}")

    # Inject Hermes learned rules into Groq prompt
    base_prompt = "\n\n".join(filter(None, [
        f"<context>\n{schema}\n</context>" if schema else "",
        f"## USER INSTRUCTIONS — FOLLOW STRICTLY (these override Figma/image if conflict):\n{extra_prompt.strip()}" if extra_prompt and extra_prompt.strip() else "",
        "Convert this UI structure to Vivid layout JSON. Use EXACT colors, text, layout. Apply user instructions above. Keep JSON compact.\n\n" + analysis_text,
        "Output valid JSON only. No explanation, no markdown. Start with {"
    ]))
    full_prompt = inject_learned_rules(base_prompt)

    print(f"[groq] generating from structured analysis...")
    raw = await call_groq_text(full_prompt, max_tokens=max_tokens)
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'^```\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'```\s*$', '', raw)
    f, l = raw.find('{'), raw.rfind('}')
    if f != -1 and l != -1: raw = raw[f:l+1]

    if raw.startswith('{') or raw.startswith('['):
        try:
            parsed = post_process(json.loads(raw))

            # ── Hermes Validation ──────────────────────────────────
            validation = await hermes_validate(parsed)
            score  = validation.get("score", 100)
            issues = validation.get("issues", [])
            if issues:
                print(f"[hermes-validate] score={score} found {len(issues)} issues — triggering review")
                asyncio.create_task(hermes_review_and_learn(parsed, "; ".join(issues[:3])))

            return {
                "data":   parsed,
                "raw":    json.dumps(parsed),
                "hermes": {"score": score, "issues": issues, "rules_loaded": len(load_learned_rules())}
            }
        except json.JSONDecodeError as e:
            print(f"[groq] JSON parse failed: {e}")
            asyncio.create_task(hermes_review_and_learn({}, f"JSON parse error: {str(e)[:100]}"))
            try:
                last_brace = raw.rfind('}')
                if last_brace > 0:
                    parsed = post_process(json.loads(raw[:last_brace + 1]))
                    print(f"[groq] salvaged truncated JSON")
                    return {"data": parsed, "raw": json.dumps(parsed), "hermes": {"score": 50, "issues": ["truncated JSON salvaged"]}}
            except Exception:
                pass
        except Exception as e:
            print(f"[groq] error: {e}")
    return {"data": None, "raw": raw, "hermes": {"score": 0, "issues": ["generation failed"]}}
async def generate_from_text(prompt: str) -> dict:
    schema = get_schema()
    full_prompt = "\n\n".join(filter(None, [
        f"<context>\n{schema}\n</context>" if schema else "",
        f"Generate a Vivid layout JSON for:\n{prompt}",
        "\n\nIMPORTANT: Output valid JSON only. No explanation, no markdown. Start with {"
    ]))
    print(f"[groq] generating from text prompt...")
    raw = await call_groq_text(full_prompt)
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'^```\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'```\s*$', '', raw)
    f, l = raw.find('{'), raw.rfind('}')
    if f != -1 and l != -1: raw = raw[f:l+1]
    if raw.startswith('{') or raw.startswith('['):
        try:
            parsed = post_process(json.loads(raw))
            return {"data": parsed, "raw": json.dumps(parsed)}
        except json.JSONDecodeError as e:
            print(f"[groq] JSON parse failed: {e}")
            try:
                last_brace = raw.rfind('}')
                if last_brace > 0:
                    salvaged = raw[:last_brace + 1]
                    parsed = post_process(json.loads(salvaged))
                    print(f"[groq] salvaged truncated JSON successfully")
                    return {"data": parsed, "raw": json.dumps(parsed)}
            except Exception as e2:
                print(f"[groq] salvage also failed: {e2}")
        except Exception as e:
            print(f"[groq] JSON parse failed: {e}")
    return {"data": None, "raw": raw}
class RunRequest(BaseModel):
    prompt:    str = ""
    image:     str | None = None
    imageType: str = "image/png"
    figmaUrl:  str | None = None

class GenerateRequest(BaseModel):
    structure: str = ""
    prompt:    str = ""
    figmaUrl:  str | None = None
    image:     str | None = None
    imageType: str = "image/png"

class SaveDbRequest(BaseModel):
    layoutJson: str
    layoutName: str
    subscriberId: int
    journeyId: str = ""
    dbHost: str
    dbPort: int = 1521
    dbService: str
    dbUser: str
    dbPassword: str

# ── POST /api/run — SSE streaming (direct UI path) ─────────────────
@app.post("/api/run")
async def run_prompt(req: RunRequest):
    async def stream():
        def sse(ev, d): return f"event: {ev}\ndata: {json.dumps(d)}\n\n"

        try:
            result = None

            if req.figmaUrl:
                # ── FIGMA MCP PATH ──────────────────────────────────
                yield sse("progress", {"step": 1, "message": "🎨 Fetching Figma design via MCP..."})
                try:
                    # Get exact colors from MCP
                    mcp_data   = await get_figma_design_via_mcp(req.figmaUrl)
                    mcp_colors = extract_colors_from_mcp(mcp_data)
                    merged     = merge_color_sources(mcp_colors, [])
                    yield sse("progress", {"step": 1, "message": f"✓ {len(merged['palette'])} exact colors extracted from Figma"})

                    # Get screenshot for layout detection
                    yield sse("progress", {"step": 1, "message": "📸 Capturing Figma screenshot for layout..."})
                    try:
                        fig_img, fig_type = await get_figma_screenshot(req.figmaUrl)
                        structured = await extract_layout_via_vision(fig_img, fig_type, merged)
                    except Exception as e:
                        print(f"[figma-screenshot] failed: {e} — using text prompt")
                        structured = req.prompt or "Create a layout based on the Figma design"

                    yield sse("analysis", {"structure": structured})
                    yield sse("progress", {"step": 1, "message": "✓ Layout & colors ready"})
                    yield sse("progress", {"step": 2, "message": "⚡ Generating Vivid JSON..."})
                    if req.prompt and req.prompt.strip():
                        structured = f"{structured}\n\nUSER INSTRUCTIONS (follow strictly, override if conflict):\n{req.prompt.strip()}"
                    result = await generate_from_structured(structured, "")

                except Exception as e:
                    print(f"[figma-mcp] error: {e}")
                    yield sse("progress", {"step": 1, "message": f"⚠ Figma failed: {str(e)[:60]} — falling back to text..."})
                    result = await generate_from_text(req.prompt or "Create a simple page layout")
                    result = await generate_from_text(req.prompt or "Create a simple page layout")

            elif req.image:
                # IMAGE PATH — vision → structured → generate
                yield sse("progress", {"step": 1, "message": "🎨 Extracting colors & structure..."})
                structured = ""
                try:
                    structured = await analyze_image_structured(req.image, req.imageType)
                    yield sse("analysis", {"structure": structured})
                    yield sse("progress", {"step": 1, "message": "✓ Colors & layout captured"})
                except Exception as e:
                    print(f"[stage1] error: {e}")
                    yield sse("progress", {"step": 1, "message": "⚠ Vision failed, using prompt..."})

                yield sse("progress", {"step": 2, "message": "⚡ Generating Vivid JSON..."})
                if structured:
                    if req.prompt and req.prompt.strip():
                        structured = f"{structured}\n\nUSER INSTRUCTIONS (follow strictly, override if conflict):\n{req.prompt.strip()}"
                    result = await generate_from_structured(structured, "")
                else:
                    result = await generate_from_text(req.prompt or "Create a simple page layout")
            else:
                # TEXT PATH
                yield sse("progress", {"step": 2, "message": "⚡ Generating Vivid JSON..."})
                result = await generate_from_text(req.prompt or "Create a simple page layout")

            yield sse("result", {"source": "groq", "data": result["data"], "raw": result["raw"]})
            yield sse("done", {})

        except Exception as e:
            print(f"[run] error: {e}")
            yield sse("error", {"message": str(e)})

    return StreamingResponse(stream(), media_type="text/event-stream")

# ── POST /api/generate — n8n path ─────────────────────────────────
@app.post("/api/generate")
async def generate(req: GenerateRequest):
    print(f"[n8n] figmaUrl={bool(req.figmaUrl)} image={bool(req.image)} structure={req.structure[:60] if req.structure else ''}")

    # ── FIGMA URL PATH ──────────────────────────────────────────────
    if req.figmaUrl:
        print(f"[n8n] Figma MCP path: {req.figmaUrl[:60]}")
        try:
            # Get exact colors from MCP
            mcp_data   = await get_figma_design_via_mcp(req.figmaUrl)
            mcp_colors = extract_colors_from_mcp(mcp_data)
            merged     = merge_color_sources(mcp_colors, [])
            print(f"[n8n] MCP colors: {merged['palette'][:5]}")

            # Get screenshot for layout detection
            try:
                fig_img, fig_type = await get_figma_screenshot(req.figmaUrl)
                structured = await extract_layout_via_vision(fig_img, fig_type, merged)
            except Exception as e:
                print(f"[n8n] screenshot failed: {e} — using prompt")
                structured = req.prompt or "Create a layout based on the Figma design"

        except Exception as e:
            print(f"[n8n] Figma REST API failed: {e} — trying screenshot+vision fallback")
            try:
                # Fallback: get screenshot → Pillow colors → vision layout
                fig_img, fig_type = await get_figma_screenshot(req.figmaUrl)
                pixel_colors      = extract_dominant_colors(fig_img)
                fallback_merged   = merge_color_sources({}, pixel_colors)
                structured        = await extract_layout_via_vision(fig_img, fig_type, fallback_merged)
                print(f"[n8n] screenshot fallback succeeded")
            except Exception as e2:
                print(f"[n8n] screenshot fallback also failed: {e2} — using prompt only")
                structured = req.prompt or "Create a simple page layout"

    # ── IMAGE PATH ─────────────────────────────────────────────────
    elif req.image:
        print(f"[n8n] image vision path")
        try:
            structured = await analyze_image_structured(req.image, req.imageType)
        except Exception as e:
            print(f"[n8n] vision failed: {e}")
            structured = req.prompt or "Create a simple page layout"

    # ── TEXT / STRUCTURE PATH ───────────────────────────────────────
    else:
        structured = req.structure or req.prompt
        if not structured:
            raise HTTPException(400, "No input — provide structure, prompt, image, or figmaUrl")

    # ── GENERATE ───────────────────────────────────────────────────
    if req.prompt and req.prompt.strip():
        structured = f"{structured}\n\nUSER INSTRUCTIONS (follow strictly, override if conflict):\n{req.prompt.strip()}"
    result = await generate_from_structured(structured, "")
    processed = post_process(result["data"]) if result["data"] else None
    return {
        "success": True,
        "data":    processed,
        "raw":     json.dumps(processed) if processed else result["raw"]
    }

# ── POST /api/save-db ──────────────────────────────────────────────
@app.post("/api/save-db")
async def save_db(req: SaveDbRequest):
    import oracledb
    try:
        raw = req.layoutJson.strip()
        f, l = raw.find("{"), raw.rfind("}")
        if f != -1 and l != -1: raw = raw[f:l+1]
        parsed = json.loads(raw)
        db_json_str = json.dumps(parsed if "layout" in parsed else {"layout": parsed})
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    conn = None
    try:
        conn = oracledb.connect(
            user=req.dbUser, password=req.dbPassword,
            dsn=f"{req.dbHost}:{req.dbPort}/{req.dbService}"
        )
        with conn.cursor() as cur:
            cur.execute("SELECT NVL(MAX(VIVIDLAYOUTID),0)+1 FROM vividlayoutmaster")
            new_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO vividlayoutmaster (SUBSCRIBERID,VIVIDLAYOUTID,SUBCATEGORYID,NAME,DESCRIPTION) VALUES(:1,:2,-1,:3,NULL)",
                [req.subscriberId, new_id, req.layoutName]
            )
            chunks = [db_json_str[i:i+3000] for i in range(0, len(db_json_str), 3000)]
            vd  = "; ".join(f"v_sql{i+1} NCLOB" for i in range(len(chunks))) + ";"
            va  = "\n".join(f"v_sql{i+1} := '{c.replace(chr(39), chr(39)*2)}';" for i, c in enumerate(chunks))
            cc  = " || ".join(f"v_sql{i+1}" for i in range(len(chunks)))
            cur.execute(f"""DECLARE v_sql NCLOB; {vd}
BEGIN
{va}
  v_sql := {cc};
  INSERT INTO vividlayouttemplate(SUBSCRIBERID,APPLICATIONID,LAYOUTID,LAYOUTTYPEID,STATUSID,ISPUBLISH,VERSION,LAYOUTJSON,JOURNEYID,CREATEDON,MODIFIEDON)
  VALUES({req.subscriberId},1,{new_id},1,1,0,'1.0',v_sql,'{req.journeyId}',SYSDATE,SYSDATE);
END;""")
            conn.commit()
            print(f"[db] saved layout ID: {new_id}")
        return {"success": True, "layoutId": new_id, "layoutName": req.layoutName}
    except Exception as e:
        if conn: conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        if conn: conn.close()

# ── GET /api/files ─────────────────────────────────────────────────
@app.get("/api/files")
def list_files():
    files = sorted(
        [{"name": f.name, "modified": f.stat().st_mtime * 1000}
         for f in OUTPUT_DIR.glob("*.json")],
        key=lambda x: -x["modified"]
    )[:20]
    return {"files": files}

@app.get("/api/file/{name}")
def get_file(name: str):
    safe = OUTPUT_DIR / Path(name).name
    if not safe.exists():
        raise HTTPException(404, "Not found")
    content = safe.read_text(encoding="utf-8")
    return {"filename": name, "data": json.loads(content), "raw": content}

# ── GET /api/hermes-report ────────────────────────────────────────
@app.get("/api/hermes-report")
def hermes_report():
    hermes_up = False
    try:
        import httpx as _h
        r = _h.get("http://localhost:11434/api/tags", timeout=2)
        hermes_up = r.status_code == 200
    except Exception:
        pass
    return {
        "hermes_enabled": HERMES_ENABLED,
        "hermes_online":  hermes_up,
        "hermes_model":   HERMES_MODEL,
        "rules_count":    len(load_learned_rules()),
        "rules":          load_learned_rules()
    }

# ── POST /api/flag-layout ─────────────────────────────────────────
class FlagRequest(BaseModel):
    layoutJson: str
    issue: str = "Designer crash or incorrect output"

@app.post("/api/flag-layout")
async def flag_layout(req: FlagRequest):
    try:
        parsed = json.loads(req.layoutJson)
    except Exception:
        parsed = {}
    new_rules = await hermes_review_and_learn(parsed, req.issue)
    return {
        "success":     True,
        "new_rules":   new_rules,
        "total_rules": len(load_learned_rules()),
        "message":     f"Hermes learned {len(new_rules)} new rules from this feedback"
    }

# ── DELETE /api/hermes-rules ──────────────────────────────────────
@app.delete("/api/hermes-rules")
def clear_hermes_rules():
    try:
        if LEARNED_RULES.exists():
            LEARNED_RULES.unlink()
        return {"success": True, "message": "Hermes rules cleared"}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Serve index.html ───────────────────────────────────────────────
from fastapi.responses import FileResponse

@app.get("/")
def serve_index():
    index = OUTPUT_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "Vivid Layout Generator — Python/Groq running", "port": 8000}

if __name__ == "__main__":
    import uvicorn
    print("\n  Vivid Layout Generator — BusinessNext")
    print(f"  → http://localhost:8000")
    print(f"  → Groq Model  : {GROQ_MODEL}")
    print(f"  → Groq Key    : {'✓ set' if GROQ_API_KEY else '✗ MISSING — set GROQ_API_KEY in .env'}")
    print(f"  → Figma Token : {'✓ set' if FIGMA_TOKEN else '✗ MISSING — set FIGMA_TOKEN in .env'}")
    print(f"  → Schema      : {'✓ found' if CLAUDE_GROQ.exists() else '✗ NOT found'}")
    print(f"  → Hermes      : {'enabled' if HERMES_ENABLED else 'disabled'} ({HERMES_MODEL} @ {OLLAMA_URL})")
    print(f"  → Learned Rules: {len(load_learned_rules())} rules loaded\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)