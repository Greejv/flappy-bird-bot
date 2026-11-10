"""Convert docs/TUTORIAL.md into a standalone TUTORIAL.html for the zip.

usage: python scripts/tutorial_html.py OUT_DIR   (needs: pip install markdown)
Writes OUT_DIR/TUTORIAL.html and copies the images to OUT_DIR/images/.
"""
import os
import shutil
import sys

import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1]
src = open(os.path.join(ROOT, "docs", "TUTORIAL.md"), encoding="utf-8").read()
body = markdown.markdown(src, extensions=["tables", "fenced_code"])
html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Flappy Money Bot – Install tutorial</title>
<style>
body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 860px; margin: 0 auto;
       padding: 24px 16px 80px; line-height: 1.55; color: #1d1d1f; background: #fff; }}
img {{ max-width: 100%; border-radius: 10px; margin: 8px 0 18px; }}
code, pre {{ background: #f2f2f5; border-radius: 6px; }} code {{ padding: 1px 5px; }}
pre {{ padding: 12px; overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; }} td, th {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
blockquote {{ background: #fff8e1; border-left: 4px solid #ffb300; margin: 12px 0; padding: 8px 14px; border-radius: 6px; }}
h2 {{ margin-top: 40px; border-top: 1px solid #eee; padding-top: 24px; }}
</style></head><body>{body}</body></html>"""
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "TUTORIAL.html"), "w", encoding="utf-8") as f:
    f.write(html)
shutil.copytree(os.path.join(ROOT, "docs", "images"), os.path.join(out, "images"), dirs_exist_ok=True)
print("wrote", os.path.join(out, "TUTORIAL.html"))
