#!/bin/sh
# Get ready for iVendNext in one line, on macOS or Linux:
#
#     curl -fsSL https://developer.ivendnext.com/install.sh | sh
#
# It puts the iVendNext partner kit in ~/.ivendnext/kit (a git clone where git is here, else GitHub's archive of main),
# puts the ivn command in ~/.local/bin and that folder on your PATH for good (your shell's start file, once), and runs
# ivn doctor. Run it again to update the kit in place. It asks nothing and needs no administrator rights. Nothing of
# iVendNext itself is installed: your sites are ours, in the cloud.
#
# The kit is github.com/ivendnext-developers/partner-kit; this file is its site/install.sh.
set -eu

HOME_DIR="${IVN_HOME:-$HOME/.ivendnext}"
KIT="$HOME_DIR/kit"
BIN="${IVN_BIN:-$HOME/.local/bin}"
REPO="${IVN_KIT_REPO:-https://github.com/ivendnext-developers/partner-kit.git}"
ARCHIVE="${IVN_KIT_ARCHIVE:-https://github.com/ivendnext-developers/partner-kit/archive/refs/heads/main.zip}"
MARK="# the ivn command (iVendNext partner kit)"

say() { printf '%s\n' "$*"; }
stop() { say "$*"; exit 1; }

say "Getting ready for iVendNext. Nothing of iVendNext goes on this computer: your sites are ours, in the cloud."

# 1. Python: ivn runs on it
PY=""
for p in python3 python; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    PY="$p"; break
  fi
done
if [ -z "$PY" ]; then
  if [ "$(uname -s)" = "Darwin" ]; then
    stop "Python 3.9 or newer is needed and was not found. Install it with: xcode-select --install (it brings git too), then run this line again."
  fi
  stop "Python 3.9 or newer is needed and was not found. Install it with your system's packages (for example: sudo apt install python3 git), then run this line again."
fi
say "Python: $("$PY" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'), new enough."

# 2. the kit
HAS_GIT=""
if command -v git >/dev/null 2>&1 && git --version >/dev/null 2>&1; then HAS_GIT=1; fi
mkdir -p "$HOME_DIR"
if [ -d "$KIT/.git" ]; then
  if [ -z "$HAS_GIT" ]; then stop "The kit in $KIT is a git clone and git is not on this computer. Install git, then run this line again."; fi
  say "Updating the kit in $KIT."
  (cd "$KIT" && "$PY" tools/ivn/ivn.py update) || stop "The kit was not updated. Its folder is as it was."
elif [ -d "$KIT" ] && [ -f "$KIT/tools/ivn/ivn.py" ]; then
  say "Updating the kit in $KIT."
  "$PY" "$KIT/tools/ivn/ivn.py" update || stop "The kit was not updated. Its folder is as it was."
elif [ -n "$HAS_GIT" ]; then
  say "Fetching the kit into $KIT with git."
  rm -rf "$KIT"
  git clone --quiet --depth 1 "$REPO" "$KIT" || stop "The kit could not be fetched. Check your connection and run this line again."
else
  say "Fetching the kit into $KIT (git is not here, so as GitHub's archive; install git to use ivn pull)."
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  curl -fsSL "$ARCHIVE" -o "$TMP/kit.zip" || stop "The kit could not be fetched. Check your connection and run this line again."
  "$PY" - "$TMP/kit.zip" "$TMP/out" <<'PY'
import pathlib, sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
out = pathlib.Path(sys.argv[2])
z.extractall(out)
top = next(out.iterdir())
for info in z.infolist():   # keep the launchers runnable
    if (info.external_attr >> 16) & 0o111:
        p = out / info.filename
        p.chmod(p.stat().st_mode | 0o755)
(top / ".kit-commit").write_text((z.comment or b"").decode("ascii", "replace").strip() + "\n")
top_name = z.namelist()[0].split("/", 1)[0] + "/"
(top / ".kit-files").write_text("\n".join(sorted(n[len(top_name):] for n in z.namelist() if not n.endswith("/") and n[len(top_name):])) + "\n")
PY
  rm -rf "$KIT"
  mv "$TMP/out/"* "$KIT"
fi

# 3. ivn on the PATH, for good
mkdir -p "$BIN"
cat > "$BIN/ivn" <<EOF
#!/bin/sh
# the ivn command, written by the iVendNext installer: it runs the kit's ivn in $KIT
exec $PY "$KIT/tools/ivn/ivn.py" "\$@"
EOF
chmod 755 "$BIN/ivn"
say "The ivn command: $BIN/ivn"

case "$(basename "${SHELL:-sh}")" in
  zsh) RC="$HOME/.zshrc"; LINE="export PATH=\"$BIN:\$PATH\"" ;;
  bash) if [ "$(uname -s)" = "Darwin" ]; then RC="$HOME/.bash_profile"; else RC="$HOME/.bashrc"; fi; LINE="export PATH=\"$BIN:\$PATH\"" ;;
  fish) RC="$HOME/.config/fish/config.fish"; LINE="set -gx PATH \"$BIN\" \$PATH" ;;
  *) RC="$HOME/.profile"; LINE="export PATH=\"$BIN:\$PATH\"" ;;
esac
NEW_WINDOW=""
if [ -f "$RC" ] && grep -qF "$MARK" "$RC"; then
  say "Your PATH: $RC has the ivn line already."
else
  mkdir -p "$(dirname "$RC")"
  printf '\n%s\n%s\n' "$MARK" "$LINE" >> "$RC"
  say "Your PATH: added $BIN to $RC, so every new terminal window has ivn."
fi
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) NEW_WINDOW=1 ;;
esac

# 4. what this computer has, and what to run next
say ""
"$BIN/ivn" doctor || true
if [ -n "$NEW_WINDOW" ]; then
  say ""
  say "Open a new terminal window for ivn to be found there, or type: export PATH=\"$BIN:\$PATH\""
fi
