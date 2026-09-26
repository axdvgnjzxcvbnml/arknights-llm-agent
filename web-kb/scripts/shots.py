import sys, time
from playwright.sync_api import sync_playwright

SHOTS = "/mnt/agents/output/shots"
PAGES = [
    ("rag.png", "/rag?q=高防御敌人怎么打", 1600, 1500),
    ("graph.png", "/graph", 1600, 1100),
    ("graph-focus.png", "/graph?focus=碎骨", 1600, 1100),
    ("operator.png", "/operator", 1600, 1500),
]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/usr/bin/chromium",
                                args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
    for name, path, w, h in PAGES:
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        page.goto(f"http://127.0.0.1:4173{path}", wait_until="networkidle")
        page.wait_for_timeout(2500)  # 等待力导向布局稳定 / 检索完成
        page.screenshot(path=f"{SHOTS}/{name}", full_page=True)
        print("saved", name)
        page.close()
    browser.close()
