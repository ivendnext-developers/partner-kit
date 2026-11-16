"""Put receipt.html and logo.png into the manifest's receipt (the logo is inlined as a data address, so the receipt has
no outside fetch). Edit receipt.html, or replace logo.png (a small PNG, under 20 kB), then run, from this folder:

    python3 build.py

It changes the receipt's layout and nothing else in the manifest. Here in the kit it writes this sample's manifest.json;
in an app made from this sample (this file at service/<tag>/build.py) it writes the app's own manifest.json, the one the
site installs, and the copy this sample's own tests read (tests/<tag>/_manifest.json). Then run `ivn check`."""
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "PP RCP UAE Tax Invoice"     # the receipt's print format (in an app made from this sample, its name there)


def targets() -> list:
    """The manifests that carry the receipt: the app's own and its tests' copy in a made app, else this folder's."""
    app = os.path.dirname(os.path.dirname(HERE))
    if os.path.isfile(os.path.join(app, "service", "dispatch.json")):         # an app New app made
        found = [os.path.join(app, "manifest.json"), os.path.join(app, "tests", os.path.basename(HERE), "_manifest.json")]
    else:
        found = [os.path.join(HERE, "manifest.json")]
    return [p for p in found if os.path.isfile(p)]


def main() -> int:
    html = open(os.path.join(HERE, "receipt.html"), encoding="utf-8").read()
    logo = base64.b64encode(open(os.path.join(HERE, "logo.png"), "rb").read()).decode()
    layout = html.replace("@@LOGO@@", logo)
    paths = targets()
    if not paths:
        print("no manifest.json found to write the receipt into", file=sys.stderr)
        return 1
    for path in paths:
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
        formats = [p for p in manifest.get("print_formats") or [] if p.get("name") == NAME]
        if len(formats) != 1:
            print(f"{os.path.relpath(path)} has no print format named {NAME}: put that name back, or write its new name "
                  "in NAME at the top of build.py", file=sys.stderr)
            return 1
        formats[0]["html"] = layout
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"{os.path.relpath(path)} written, {len(layout)} characters of template")
    return 0


if __name__ == "__main__":
    sys.exit(main())
