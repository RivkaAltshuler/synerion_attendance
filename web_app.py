from __future__ import annotations

import os
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request


def resolve_base_dir() -> Path:
  # In PyInstaller onefile, __file__ points to a temp extraction directory.
  # Use the executable directory so release-side EXEs are discoverable.
  if getattr(sys, "frozen", False):
    return Path(sys.executable).resolve().parent
  return Path(__file__).resolve().parent


BASE_DIR = resolve_base_dir()
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

jobs_lock = threading.Lock()
jobs: dict[str, dict] = {}


HTML_PAGE = """
<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>סינריון - העלאת PDF</title>
  <style>
    :root {
      --bg: #f3efe6;
      --panel: #fffaf2;
      --ink: #1f2a2d;
      --muted: #617174;
      --line: #d8cdbd;
      --accent: #0f766e;
      --accent-2: #c7702e;
      --danger: #b42318;
      --shadow: 0 24px 60px rgba(60, 44, 20, 0.12);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Noto Sans Hebrew", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, rgba(199,112,46,0.18), transparent 28%),
        radial-gradient(circle at bottom left, rgba(15,118,110,0.18), transparent 32%),
        linear-gradient(135deg, #efe6d8, var(--bg));
      min-height: 100vh;
    }

    .shell {
      max-width: 1080px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }

    .hero {
      display: grid;
      gap: 20px;
      margin-bottom: 24px;
    }

    .badge {
      width: fit-content;
      padding: 8px 14px;
      border: 1px solid rgba(15,118,110,0.25);
      border-radius: 999px;
      background: rgba(255,255,255,0.65);
      color: var(--accent);
      font-size: 14px;
    }

    h1 {
      margin: 0;
      font-size: clamp(36px, 6vw, 68px);
      line-height: 0.95;
      letter-spacing: -0.04em;
    }

    .sub {
      max-width: 760px;
      color: var(--muted);
      font-size: 18px;
      line-height: 1.7;
      margin: 0;
    }

    .grid {
      display: grid;
      grid-template-columns: 1.05fr 0.95fr;
      gap: 22px;
    }

    .panel {
      background: rgba(255,250,242,0.88);
      backdrop-filter: blur(8px);
      border: 1px solid rgba(216,205,189,0.9);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 24px;
    }

    .panel h2 {
      margin: 0 0 8px;
      font-size: 22px;
    }

    .hint {
      color: var(--muted);
      margin: 0 0 18px;
      line-height: 1.6;
    }

    .dropzone {
      border: 2px dashed rgba(15,118,110,0.25);
      border-radius: 24px;
      padding: 24px;
      background: rgba(255,255,255,0.7);
      transition: border-color 0.2s ease, transform 0.2s ease;
    }

    .dropzone:hover {
      border-color: rgba(15,118,110,0.5);
      transform: translateY(-1px);
    }

    input[type=file] {
      width: 100%;
      font: inherit;
      color: var(--ink);
    }

    .file-name {
      margin-top: 14px;
      color: var(--accent-2);
      font-weight: 600;
      min-height: 24px;
    }

    .actions {
      display: grid;
      gap: 12px;
      margin-top: 20px;
    }

    .action-btn {
      width: 100%;
      border: 0;
      border-radius: 18px;
      padding: 16px 18px;
      font: inherit;
      font-size: 17px;
      font-weight: 700;
      cursor: pointer;
      transition: transform 0.16s ease, opacity 0.16s ease, box-shadow 0.16s ease;
      color: white;
      box-shadow: 0 14px 30px rgba(31,42,45,0.16);
    }

    .action-btn:hover { transform: translateY(-1px); }
    .action-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

    .summary { background: linear-gradient(135deg, #0f766e, #178f84); }
    .verify { background: linear-gradient(135deg, #c7702e, #dd8d42); }
    .auto { background: linear-gradient(135deg, #93441f, #b15e2f); }

    .status-card {
      display: grid;
      gap: 14px;
      min-height: 100%;
    }

    .status-line {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }

    .pill {
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(15,118,110,0.12);
      color: var(--accent);
      font-weight: 700;
      font-size: 14px;
    }

    .pill.error {
      background: rgba(180,35,24,0.12);
      color: var(--danger);
    }

    .log {
      margin: 0;
      padding: 18px;
      min-height: 380px;
      border-radius: 20px;
      background: #1c2527;
      color: #eff6f3;
      overflow: auto;
      white-space: pre-wrap;
      line-height: 1.55;
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 14px;
    }

    .tips {
      display: grid;
      gap: 10px;
      margin-top: 12px;
      color: var(--muted);
      line-height: 1.6;
      font-size: 14px;
    }

    @media (max-width: 860px) {
      .grid { grid-template-columns: 1fr; }
      .panel { padding: 20px; border-radius: 22px; }
      .log { min-height: 280px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="badge">ממשק מקומי לסינריון</div>
      <h1>מעלים PDF, בודקים, ואז מדווחים.</h1>
      <p class="sub">המסך הזה רץ רק על המחשב המקומי. הקובץ נשאר אצלך, והכלי מאחורי הקלעים מפעיל את אותו מנגנון שכבר עובד מול מל"מ וסינריון.</p>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>קובץ דוח</h2>
        <p class="hint">בחרי את קובץ ה־PDF שהופק ממל"מ. אחר כך אפשר לבחור אם לבצע בדיקה בלבד, אימות מול סינריון, או דיווח אוטומטי.</p>

        <div class="dropzone">
          <input id="pdf-input" type="file" accept=".pdf,application/pdf">
          <div id="file-name" class="file-name">עדיין לא נבחר קובץ</div>
        </div>

        <div class="actions">
          <button class="action-btn summary" data-mode="summary">בדיקת PDF בלבד</button>
          <button class="action-btn verify" data-mode="verify">אימות מול סינריון</button>
          <button class="action-btn auto" data-mode="auto">דיווח אוטומטי לסינריון</button>
        </div>

        <div class="tips">
          <div>בדיקה בלבד לא פותחת את סינריון.</div>
          <div>אימות ודיווח יפתחו דפדפן אמיתי וידרשו התחברות.</div>
          <div>חופשה ומחלה עדיין מוזנים ידנית בתוך סינריון.</div>
        </div>
      </div>

      <div class="panel status-card">
        <div class="status-line">
          <div>
            <h2 style="margin: 0 0 4px;">פלט ריצה</h2>
            <div class="hint" style="margin: 0;">הלוג כאן מתעדכן בזמן אמת.</div>
          </div>
          <div id="status-pill" class="pill">מוכן</div>
        </div>

        <pre id="log" class="log">כאן יופיעו התוצאות.</pre>
      </div>
    </section>
  </div>

  <script>
    const fileInput = document.getElementById('pdf-input');
    const fileName = document.getElementById('file-name');
    const logEl = document.getElementById('log');
    const statusPill = document.getElementById('status-pill');
    const buttons = Array.from(document.querySelectorAll('.action-btn'));
    let activePoll = null;

    fileInput.addEventListener('change', () => {
      const file = fileInput.files[0];
      fileName.textContent = file ? file.name : 'עדיין לא נבחר קובץ';
    });

    function setBusy(isBusy) {
      buttons.forEach((button) => { button.disabled = isBusy; });
    }

    function setStatus(label, isError = false) {
      statusPill.textContent = label;
      statusPill.classList.toggle('error', isError);
    }

    async function startJob(mode) {
      const file = fileInput.files[0];
      if (!file) {
        setStatus('יש לבחור PDF קודם', true);
        logEl.textContent = 'לא נבחר קובץ PDF.';
        return;
      }

      if (activePoll) {
        clearInterval(activePoll);
        activePoll = null;
      }

      setBusy(true);
      setStatus('מעלה קובץ...');
      logEl.textContent = 'מעלה את הקובץ ומתחיל ריצה...';

      const formData = new FormData();
      formData.append('pdf', file);
      formData.append('mode', mode);

      const response = await fetch('/api/jobs', { method: 'POST', body: formData });
      const payload = await response.json();
      if (!response.ok) {
        setBusy(false);
        setStatus('שגיאה', true);
        logEl.textContent = payload.error || 'Failed to start job';
        return;
      }

      const jobId = payload.jobId;
      setStatus('רץ...');
      activePoll = setInterval(async () => {
        const statusResponse = await fetch(`/api/jobs/${jobId}`);
        const statusPayload = await statusResponse.json();
        logEl.textContent = statusPayload.log || '';
        logEl.scrollTop = logEl.scrollHeight;

        if (statusPayload.running) {
          const elapsed = statusPayload.elapsedSeconds || 0;
          setStatus(`רץ... ${elapsed} שניות`);
        }

        if (!statusPayload.running) {
          clearInterval(activePoll);
          activePoll = null;
          setBusy(false);
          const ok = statusPayload.exitCode === 0;
          setStatus(ok ? 'הסתיים' : 'נכשל', !ok);
        }
      }, 1000);
    }

    buttons.forEach((button) => {
      button.addEventListener('click', () => startJob(button.dataset.mode));
    });
  </script>
</body>
</html>
"""


def resolve_runner() -> list[str]:
  app_exe = BASE_DIR / "synerion_attendance.exe"
  dist_exe = BASE_DIR / "dist" / "synerion_attendance.exe"
  cwd_exe = Path.cwd() / "synerion_attendance.exe"
  env_python = os.environ.get("PYTHON_EXE")
  if env_python:
    python_exe = Path(env_python)
  else:
    python_exe = BASE_DIR / ".venv" / "Scripts" / "python.exe"
  attend_py = BASE_DIR / "attend.py"

  if app_exe.exists():
    return [str(app_exe)]
  if cwd_exe.exists():
    return [str(cwd_exe)]
  if dist_exe.exists():
    return [str(dist_exe)]
  if python_exe.exists() and attend_py.exists():
    return [str(python_exe), str(attend_py)]
  raise FileNotFoundError("No runnable application was found. Run from the release folder, or prepare the developer environment and build.")


def build_command(mode: str, pdf_path: Path) -> list[str]:
  mode_flag = {
    "summary": "--summary-only",
    "verify": "--verify",
    "auto": "--auto",
  }[mode]
  command = [*resolve_runner(), mode_flag, "--pdf", str(pdf_path), "--no-pause"]
  if mode in {"verify", "auto"}:
    command.append("--keep-browser-open")
  return command


def append_log(job_id: str, line: str) -> None:
    with jobs_lock:
        jobs[job_id]["log"].append(line)


def start_job(mode: str, pdf_path: Path) -> str:
    job_id = secrets.token_hex(8)
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "mode": mode,
            "running": True,
            "exit_code": None,
            "log": [f"Starting {mode} run for {pdf_path.name}\n"],
            "created_at": time.time(),
        }

    def worker() -> None:
      try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        sidecar_log = UPLOAD_DIR / f"{job_id}.log"
        env["SYNERION_LOG_FILE"] = str(sidecar_log)

        process = subprocess.Popen(
          build_command(mode, pdf_path),
          cwd=str(BASE_DIR),
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
          env=env,
        )

        read_pos = 0
        while True:
          if sidecar_log.exists():
            with sidecar_log.open("r", encoding="utf-8", errors="replace") as handle:
              handle.seek(read_pos)
              chunk = handle.read()
              read_pos = handle.tell()
            if chunk:
              append_log(job_id, chunk)

          if process.poll() is not None:
            break
          time.sleep(0.3)

        if sidecar_log.exists():
          with sidecar_log.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(read_pos)
            chunk = handle.read()
          if chunk:
            append_log(job_id, chunk)

        exit_code = process.wait()
      except Exception as exc:
        append_log(job_id, f"[ERROR] {exc}\n")
        exit_code = 1

      with jobs_lock:
        jobs[job_id]["running"] = False
        jobs[job_id]["exit_code"] = exit_code

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return job_id


@app.get("/")
def index():
    return render_template_string(HTML_PAGE)


@app.post("/api/jobs")
def create_job():
    mode = request.form.get("mode", "")
    uploaded = request.files.get("pdf")

    if mode not in {"summary", "verify", "auto"}:
        return jsonify({"error": "Invalid mode"}), 400
    if uploaded is None or uploaded.filename == "":
        return jsonify({"error": "PDF file is required"}), 400
    if not uploaded.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported"}), 400

    safe_name = f"{int(time.time())}_{secrets.token_hex(4)}.pdf"
    pdf_path = UPLOAD_DIR / safe_name
    uploaded.save(pdf_path)

    job_id = start_job(mode, pdf_path)
    return jsonify({"jobId": job_id})


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return jsonify({"error": "Job not found"}), 404
    elapsed_seconds = int(time.time() - job["created_at"])
    payload = {
      "running": job["running"],
      "exitCode": job["exit_code"],
      "elapsedSeconds": elapsed_seconds,
      "log": "".join(job["log"]),
    }
    return jsonify(payload)


def open_browser_later() -> None:
  time.sleep(1.0)
  url = "http://127.0.0.1:5000"
  try:
    if webbrowser.open(url):
      return
  except Exception:
    pass

  # Some locked-down Windows environments block webbrowser.open.
  if os.name == "nt":
    try:
      os.startfile(url)  # type: ignore[attr-defined]
      return
    except Exception:
      pass
    try:
      subprocess.Popen(["cmd", "/c", "start", "", url])
      return
    except Exception:
      pass
    try:
      subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process '{url}'"])
      return
    except Exception:
      pass

  # Last resort: keep running and let user open the URL manually.
  print(f"[i] Open manually: {url}")


if __name__ == "__main__":
    threading.Thread(target=open_browser_later, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False)