import sys, json, asyncio
try:
    import websockets
except ImportError:
    sys.exit("brak websockets")

PAGES = ["models", "playground", "documents", "settings"]

def lum(c):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def contrast(c1, c2):
    l1, l2 = sorted([lum(c1), lum(c2)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)

def parse_rgb(s):
    import re
    m = re.findall(r"[\d.]+", s or "")
    if len(m) >= 3:
        return tuple(float(x) for x in m[:3])
    return None

async def scan_page(ws, mid_ref, url):
    mid_ref[0] += 1
    await ws.send(json.dumps({"id": mid_ref[0], "method": "Page.enable"}))
    mid_ref[0] += 1
    await ws.send(json.dumps({"id": mid_ref[0], "method": "Page.navigate", "params": {"url": url}}))
    await asyncio.sleep(1.8)

    expr = """(() => {
      const out = [];
      const els = document.querySelectorAll('body *');
      for (const el of els) {
        if (el.children.length > 0) continue;
        const text = (el.textContent || '').trim();
        if (!text) continue;
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        // efektywne tlo: przejdz w gore po przezroczystych
        let bg = null, node = el;
        while (node && node !== document.documentElement) {
          const b = getComputedStyle(node).backgroundColor;
          if (b && !b.startsWith('rgba(0, 0, 0, 0)')) { bg = b; break; }
          node = node.parentElement;
        }
        out.push({tag: el.tagName, cls: String(el.className).slice(0, 30), text: text.slice(0, 25),
                  color: cs.color, bg: bg || 'rgb(11, 11, 12)'});
      }
      return JSON.stringify(out);
    })()"""

    mid_ref[0] += 1
    await ws.send(json.dumps({"id": mid_ref[0], "method": "Runtime.evaluate",
                              "params": {"expression": expr, "returnByValue": True}}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == mid_ref[0]:
            res = msg.get("result", {})
            if "exceptionDetails" in res:
                raise RuntimeError(f"JS error: {res['exceptionDetails'].get('exception', {}).get('description', '?')[:300]}")
            val = res.get("result", {}).get("value") if "result" in res else res.get("value")
            if val is None:
                raise RuntimeError(f"Brak wartosci w odpowiedzi: {json.dumps(msg)[:300]}")
            return json.loads(val)

async def main():
    ws_url = sys.argv[1]
    problems = []
    async with websockets.connect(ws_url, max_size=10**7) as ws:
        mid = [0]
        for p in PAGES:
            items = await scan_page(ws, mid, f"http://127.0.0.1:8000/{p}")
            for it in items:
                c = parse_rgb(it["color"]); b = parse_rgb(it["bg"])
                if not c or not b:
                    continue
                ratio = contrast(c, b)
                if ratio < 3.0:
                    problems.append((p, it["tag"], it["cls"], it["text"], round(ratio, 2), it["color"], it["bg"]))
        if problems:
            print(f"ZNALAZLEM {len(problems)} elementow o slabym kontrascie:")
            for p in problems:
                print(f"  [{p[0]}] <{p[1]} .{p[2]}> '{p[3]}' ratio={p[4]} color={p[5]} bg={p[6]}")
        else:
            print("BRAK elementow z kontrastem < 3.0 — wszystkie teksty czytelne w headless render")

asyncio.run(main())
