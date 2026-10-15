import os, sys, uuid, subprocess, tempfile, glob
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

API_KEY = os.environ.get("API_KEY", "change-me")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
PLOT_DIR = "/tmp/plots"
os.makedirs(PLOT_DIR, exist_ok=True)

app = FastAPI()
app.mount("/plots", StaticFiles(directory=PLOT_DIR), name="plots")

class Req(BaseModel):
    code: str
    stdin: str = ""
    timeout: int = 20

WRAPPER = '''
import matplotlib
matplotlib.use("Agg")
import sys, traceback
_code = open(sys.argv[1]).read()
_out = sys.argv[2]
try:
    exec(compile(_code, "<user>", "exec"), {"__name__": "__main__"})
except SystemExit:
    pass
except BaseException:
    traceback.print_exc()
    sys.exit(1)
finally:
    import matplotlib.pyplot as plt
    for i, n in enumerate(plt.get_fignums()):
        plt.figure(n).savefig(f"{_out}_{i}.png", dpi=120, bbox_inches="tight")
'''

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/run")
def run(req: Req, x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(401, "Bad API key")
    run_id = uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/user.py", "w").write(req.code)
        open(f"{d}/wrap.py", "w").write(WRAPPER)
        try:
            p = subprocess.run(
                [sys.executable, f"{d}/wrap.py", f"{d}/user.py", f"{PLOT_DIR}/{run_id}"],
                input=req.stdin, capture_output=True, text=True,
                timeout=min(req.timeout, 60), cwd=d)
            stdout, stderr, code = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired:
            stdout, stderr, code = "", "Timed out", -1
    images = [f"{BASE_URL}/plots/{os.path.basename(f)}"
              for f in sorted(glob.glob(f"{PLOT_DIR}/{run_id}_*.png"))]
    return {"stdout": stdout[:20000], "stderr": stderr[:5000],
            "exit_code": code, "image_urls": images}