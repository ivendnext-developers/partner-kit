"""`ivn new`, `ivn check` and `ivn push` through tools/ivn/ivn.cmd, against the test doors: the kit's CI runs this on a Windows
runner, so the command a Windows developer types has run on Windows. On any other system it runs `ivn.py` the same way.

    python tools/ivn/tests/windows_smoke.py
"""
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_ivn import TOKEN, Stub, serve  # noqa: E402

COMMAND = [str(HERE.parent / "ivn.cmd")] if os.name == "nt" else [sys.executable, str(HERE.parent / "ivn.py")]


def ivn(cwd, env, *argv):
    r = subprocess.run(COMMAND + list(argv), cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=600)
    print(f"$ ivn {' '.join(argv)}\n{r.stdout}{r.stderr}")
    if r.returncode:
        raise SystemExit(f"ivn {argv[0]} exited {r.returncode}")
    return r.stdout


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        stub = Stub(tmp)
        srv = serve(stub)
        stub.base = f"http://127.0.0.1:{srv.server_address[1]}"
        env = {**os.environ, "IVN_HOSTING_URL": stub.base, "IVN_TOKEN": TOKEN, "PYTHONUTF8": "1"}
        work = tmp / "repo"
        work.mkdir()
        ivn(work, env, "new", "acme_smoke", "--from", "s11")
        folder = work / "apps" / "acme_smoke"
        ivn(folder, env, "check")
        with open(folder / "README.md", "a", encoding="utf-8") as f:
            f.write("\nChanged by the smoke test.\n")
        out = ivn(folder, env, "push")
        if "/v1/draft/keep" not in stub.calls:
            raise SystemExit(f"nothing reached the doors: {stub.calls}")
        srv.shutdown()
    print("WINDOWS SMOKE GREEN" if os.name == "nt" else "SMOKE GREEN")
    return out


if __name__ == "__main__":
    main()
