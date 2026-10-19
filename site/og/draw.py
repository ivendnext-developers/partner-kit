#!/usr/bin/env python3
"""site/og/draw.py — draws the six preview images (site/assets-src/og/<kind>.png, 1200 x 630) from template.html with headless Chrome.

    python3 site/og/draw.py            # run again when a line below changes, and commit the six small PNGs

The build does not run this: it copies the PNGs, byte for byte, with the rest of site/assets-src/. They are the one generated file
the kit commits (the site's PDF step, which would draw them in the build, has not merged yet; when it has, the build can draw them
and these can go). Each is flat colour and text, well under 150 kB; test_site.py holds the size and the dimensions.
"""
import html
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets-src"
OUT = ASSETS / "og"
LINES = {"home": ("iVendNext Developers", "Build custom retail POS apps, integrations and extensions"),
         "needs": ("Needs catalogue", "What retailers ask for, and whether you can build it today"),
         "guide": ("Guide", "The ladder of ways into iVendNext, chapter by chapter"),
         "recipes": ("Recipes", "One recipe for each job, with its steps and commands"),
         "samples": ("Samples", "Small working examples of each way in, with their tests"),
         "card": ("A need, in the customer's words", "The verdict, the door and the way to build it")}
CHROME = [os.environ.get("CHROME", ""), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium"]


def main() -> int:
    chrome = next((c for c in CHROME if c and (pathlib.Path(c).exists() or subprocess.run(["which", c], capture_output=True).returncode == 0)), None)
    if not chrome:
        print("no Chrome found: set CHROME to its path")
        return 1
    template = (HERE / "template.html").read_text("utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for kind, (eyebrow, headline) in LINES.items():
            page = pathlib.Path(tmp) / f"{kind}.html"
            page.write_text(template.replace("{{assets}}", ASSETS.as_uri()).replace("{{eyebrow}}", html.escape(eyebrow))
                            .replace("{{headline}}", html.escape(headline)), "utf-8")
            target = OUT / f"{kind}.png"
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                            f"--user-data-dir={tmp}/profile", f"--screenshot={target}", "--window-size=1200,630",
                            "--virtual-time-budget=3000", page.as_uri()], check=True, capture_output=True)
            print(f"{kind}: {target.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
