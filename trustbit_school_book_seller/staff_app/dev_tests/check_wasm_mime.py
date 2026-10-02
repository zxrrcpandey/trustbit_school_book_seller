import os
import re
from playwright.sync_api import expect, sync_playwright
S=os.path.dirname(os.path.abspath(__file__))+"/"
BASE="http://127.0.0.1:8001"
EXE="/Users/warroom/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell"
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=EXE,args=["--use-fake-ui-for-media-stream","--use-fake-device-for-media-stream",f"--use-file-for-fake-video-capture={S}barcode.y4m"])
    ctx=b.new_context(viewport={"width":390,"height":844},is_mobile=True,has_touch=True)
    ctx.grant_permissions(["camera"],origin=BASE)
    ctx.add_init_script("delete window.BarcodeDetector")
    seen=[]
    def wasm_as_nginx_118(route):
        r=route.fetch(); h=dict(r.headers); h["content-type"]="application/octet-stream"; seen.append(h["content-type"])
        route.fulfill(response=r,headers=h)
    ctx.route(re.compile(r".*\.wasm$"),wasm_as_nginx_118)
    pg=ctx.new_page(); logs=[]
    pg.on("console",lambda m: logs.append(m.text))
    pg.goto(f"{BASE}/staff/login"); pg.fill("input[type=email]","staff1@example.com"); pg.fill("input[type=password]","Kgs-Test-2026!x"); pg.click("button[type=submit]")
    pg.wait_for_url(re.compile(r"/staff/$")); pg.goto(f"{BASE}/staff/transfer")
    pg.select_option("#from-wh","Stores - DCV"); pg.select_option("#to-wh","Godown - DCV")
    pg.get_by_role("button",name="📷 Scan").click()
    expect(pg.get_by_text(re.compile(r"\+1 Test Viva Maths 3")).first).to_be_visible(timeout=30000)
    print("PASS scan works with wasm served as", seen, "| console:", [l for l in logs if "wasm" in l.lower()][:2])
    b.close()
