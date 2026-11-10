"""Convert the tutorials into standalone HTML pages for the zip.

usage: python scripts/tutorial_html.py OUT_DIR   (needs: pip install markdown)
Writes OUT_DIR/TUTORIAL.html (English), OUT_DIR/NAVOD.html (Slovak) and
copies the images to OUT_DIR/images/.
"""
import os
import shutil
import sys

import re

import markdown


def github_slug(value, separator="-"):
    """Same anchors as GitHub: lowercase, drop punctuation, each space -> '-'."""
    value = re.sub(r"[^\w\- ]", "", value.strip().lower())
    return value.replace(" ", separator)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
STYLE = """
body { font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 860px; margin: 0 auto;
       padding: 24px 16px 80px; line-height: 1.55; color: #1d1d1f; background: #fff; }
img { max-width: 100%; border-radius: 10px; margin: 8px 0 18px; }
code, pre { background: #f2f2f5; border-radius: 6px; } code { padding: 1px 5px; }
pre { padding: 12px; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; } td, th { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
blockquote { background: #fff8e1; border-left: 4px solid #ffb300; margin: 12px 0; padding: 8px 14px; border-radius: 6px; }
h2 { margin-top: 40px; border-top: 1px solid #eee; padding-top: 24px; }
"""
for md_name, html_name, lang, title in (("TUTORIAL.md", "TUTORIAL.html", "en", "Flappy Money Bot – Install tutorial"),
                                        ("NAVOD.md", "NAVOD.html", "sk", "Flappy Money Bot – Návod")):
    src = open(os.path.join(ROOT, "docs", md_name), encoding="utf-8").read()
    body = markdown.markdown(src, extensions=["tables", "fenced_code", "toc"],
                             extension_configs={"toc": {"slugify": github_slug}})
    html = (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{title}</title><style>{STYLE}</style></head><body>{body}</body></html>")
    with open(os.path.join(out, html_name), "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", os.path.join(out, html_name))
shutil.copytree(os.path.join(ROOT, "docs", "images"), os.path.join(out, "images"), dirs_exist_ok=True)
