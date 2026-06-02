"""
Synerion Attendance Auto-Filler
===============================

אופציות הרצה:
--------------
  python attend.py --auto --pdf=PATH_TO_REPORT.pdf
      פותח Chrome, ממתין להתחברות ידנית, ממלא לפי השורות שנשלפו מה-PDF.

  python attend.py --auto --only-date=DD/MM/YYYY
      מריץ יום בודד בלבד, לדוגמה: --only-date=05/04/2026

  python attend.py --summary-only --pdf=PATH_TO_REPORT.pdf
      בדיקה מול דוח PDF ספציפי (קורא חודש + סה"כ שעות מתוך ה-PDF).

  python attend.py --summary-only --only-date=DD/MM/YYYY
      בדיקת סיכום שעות לתאריך בודד בלבד.

  python attend.py --auto --debug-artifacts
      כמו --auto, בנוסף שומר קבצי HTML וצילום מסך לתיקיית הפרויקט לצורכי דיבוג.

  python attend.py --verify --pdf=PATH_TO_REPORT.pdf
      אימות מול חודש/סה"כ שנקראים מקובץ PDF שסופק בפרמטר.

דרישות:
-------
  pip install -r requirements.txt
  playwright install chromium
"""

import asyncio
import builtins
import os
import re
import sys
import shutil
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

try:
    import pdfplumber
except Exception:
    pdfplumber = None


def configure_text_output() -> None:
    """Ensure redirected output streams can safely handle Unicode text."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
                write_through=True,
            )
        except Exception:
            pass


def force_flushed_print() -> None:
    original_print = builtins.print
    sidecar_path = os.environ.get("SYNERION_LOG_FILE")
    sidecar_handle = None

    if sidecar_path:
        try:
            Path(sidecar_path).parent.mkdir(parents=True, exist_ok=True)
            sidecar_handle = open(sidecar_path, "a", encoding="utf-8", buffering=1)
        except Exception:
            sidecar_handle = None

    def flushed_print(*args, **kwargs):
        kwargs.setdefault("flush", True)
        result = original_print(*args, **kwargs)
        if sidecar_handle is not None:
            try:
                sep = kwargs.get("sep", " ")
                end = kwargs.get("end", "\n")
                text = sep.join(str(arg) for arg in args) + end
                sidecar_handle.write(text)
                sidecar_handle.flush()
            except Exception:
                pass
        return result

    builtins.print = flushed_print


configure_text_output()
force_flushed_print()


def find_browser_executable() -> str:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(
        "Chrome או Edge לא נמצאו במחשב. יש להתקין אחד מהם לפני השימוש בכלי."
    )


BROWSER_EXECUTABLE = find_browser_executable()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
URL_BASE = "https://prologic.synerioncloud.com/SynerionWeb/"
URL_ATTENDANCE = "https://prologic.synerioncloud.com/SynerionWeb/#/attendance"


def get_cli_value(flag: str) -> str | None:
    """Supports both --flag=value and --flag value styles."""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg.startswith(flag + "="):
            return arg.split("=", 1)[1]
        if arg == flag and i + 1 < len(args):
            return args[i + 1]
    return None


AUTO_MODE = "--auto" in sys.argv  # skip page.pause() between days
ONLY_DATE = get_cli_value("--only-date")
SUMMARY_ONLY = "--summary-only" in sys.argv
VERIFY_MODE = "--verify" in sys.argv
VERIFY_MONTH = get_cli_value("--month")  # e.g. 02/2026
PDF_PATH = get_cli_value("--pdf")
DEBUG_ARTIFACTS = "--debug-artifacts" in sys.argv
NO_PAUSE = "--no-pause" in sys.argv
KEEP_BROWSER_OPEN = "--keep-browser-open" in sys.argv
SCREENSHOT_PATH = "attendance_done.png"

# ---------------------------------------------------------------------------
# ⚠️  SELECTORS — verify / update after first pause with Playwright Inspector
# ---------------------------------------------------------------------------
SEL = {
    # Synerion Mobile iframe + timesheet page
    "mobile_frame":     "#SdMobileFrame",
    "period_title":     "#periodHeaderTitle",
    "prev_period":      "#goPrevPeriodButton",
    "edit_button":      "#editButton",
    "save_button":      "#saveButton",
    "cancel_button":    "#cancelEditButton",

    # Day rows rendered inside the mobile app
    "day":              "attendance-day",
    "day_date":         "h2.attendance-day-date",
    "attendance_row":   "#attendanceRow",
    "absence_row":      "#fullAbsenceRow",
    "day_options":      "#openDayOptionsPopupButton",
    "hours_input":      "input.hours-input",
    "minutes_input":    "input.minutes-input",

    # Popup actions
    "add_attendance":   "הוסף זוג נוכחות",
    "add_wfh":          "הוסף עבודה מהבית",
    "add_note":         "הערה",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

async def get_mobile_frame(page: Page):
    await page.wait_for_selector(SEL["mobile_frame"], timeout=15000)
    for _ in range(40):
        for frame in page.frames:
            if "SynerionMobile" in frame.url and "#!/app/timesheet" in frame.url:
                return frame
        await asyncio.sleep(0.5)
    raise RuntimeError("Synerion Mobile timesheet iframe was not found")


async def navigate_to_attendance(page: Page):
    print("[*] Navigating to attendance page...")
    await page.goto(URL_ATTENDANCE)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(5000)
    print(f"[*] Attendance URL: {page.url}")

    if DEBUG_ARTIFACTS:
        html = await page.evaluate("() => document.documentElement.outerHTML")
        with open(r"C:\Users\rivka.altshuler\Desktop\synerion_attendance\attendance_live.html", "w", encoding="utf-8") as f:
            f.write(html)
        await page.screenshot(path=r"C:\Users\rivka.altshuler\Desktop\synerion_attendance\attendance_live.png", full_page=True)
        print("[i] Debug artifacts saved: attendance_live.html + attendance_live.png")

    frame = await get_mobile_frame(page)
    await frame.wait_for_load_state("networkidle", timeout=15000)
    await asyncio.sleep(1)
    print(f"[OK] Mobile iframe ready: {frame.url}")
    return frame


MONTH_KEYWORDS = {
    "01": ["ינו", "Jan"], "02": ["פבר", "Feb"], "03": ["מרץ", "Mar"],
    "04": ["אפר", "Apr"], "05": ["מאי", "May"], "06": ["יונ", "Jun"],
    "07": ["יול", "Jul"], "08": ["אוג", "Aug"], "09": ["ספט", "Sep"],
    "10": ["אוק", "Oct"], "11": ["נוב", "Nov"], "12": ["דצמ", "Dec"],
}


async def navigate_to_month(frame, month_year: str) -> None:
    """month_year = MM/YYYY e.g. '02/2026'"""
    mm, yyyy = month_year.split("/")
    keywords = MONTH_KEYWORDS.get(mm, [mm])
    for _ in range(12):
        title = (await frame.locator(SEL["period_title"]).inner_text()).strip()
        print(f"    Current period: {title}")
        if yyyy in title and any(kw in title for kw in keywords):
            print(f"[OK] Arrived at {month_year}")
            return
        await frame.locator(SEL["prev_period"]).click()
        await asyncio.sleep(1.2)
    raise RuntimeError(f"Could not navigate to {month_year}")





async def ensure_edit_mode(frame) -> bool:
    save_btn = frame.locator(SEL["save_button"])
    if await save_btn.count() and await save_btn.first.is_visible():
        return True
    edit_btn = frame.locator(SEL["edit_button"])
    if not (await edit_btn.count() and await edit_btn.first.is_visible()):
        print("[i] Edit button was not found. The month is probably locked or approved.")
        return False
    await edit_btn.first.click()
    await save_btn.first.wait_for(timeout=5000)
    print("[OK] Edit mode enabled")
    return True


async def first_visible(locator):
    count = await locator.count()
    for index in range(count):
        candidate = locator.nth(index)
        if await candidate.is_visible():
            return candidate
    return None


async def visible_items(locator):
    items = []
    count = await locator.count()
    for index in range(count):
        candidate = locator.nth(index)
        if await candidate.is_visible():
            items.append(candidate)
    return items


async def get_day(frame, date_short: str):
    days = frame.locator(SEL["day"]).filter(has_text=date_short)
    count = await days.count()
    for index in range(count):
        day = days.nth(index)
        if await day.is_visible():
            await day.scroll_into_view_if_needed()
            return day
    raise RuntimeError(f"Day row for {date_short} was not found")


async def click_popup_action(frame, label: str) -> None:
    action = await first_visible(frame.get_by_text(label, exact=True))
    if action is None:
        raise RuntimeError(f"Popup action '{label}' was not found")
    await action.click()
    await asyncio.sleep(0.7)


async def open_day_options(day) -> None:
    button = await first_visible(day.locator(SEL["day_options"]))
    if button is None:
        raise RuntimeError("Day options button was not found")
    await button.click()
    await asyncio.sleep(0.5)


async def set_input_value(locator, value: str) -> None:
    await locator.click()
    await locator.fill(value)


async def wait_for_time_inputs(day) -> bool:
    for _ in range(20):
        hours = await visible_items(day.locator(SEL["hours_input"]))
        minutes = await visible_items(day.locator(SEL["minutes_input"]))
        if len(hours) >= 2 and len(minutes) >= 2:
            return True
        await asyncio.sleep(0.3)
    return False


async def ensure_attendance_pair(frame, day) -> bool:
    if await wait_for_time_inputs(day):
        return True
    await open_day_options(day)
    await click_popup_action(frame, SEL["add_attendance"])
    return await wait_for_time_inputs(day)


async def ensure_work_from_home(frame, day) -> None:
    await open_day_options(day)
    await click_popup_action(frame, SEL["add_wfh"])


async def add_note(frame, day, note_text: str) -> bool:
    if not note_text:
        return True
    try:
        await open_day_options(day)
        await click_popup_action(frame, SEL["add_note"])
        await asyncio.sleep(0.7)

        note_inputs = await visible_items(frame.locator("textarea"))
        if not note_inputs:
            note_inputs = await visible_items(frame.locator("input[type='text']"))
        if not note_inputs:
            raise RuntimeError("Note input was not found")

        await note_inputs[-1].fill(note_text)

        save_buttons = await visible_items(frame.get_by_text("שמור", exact=True))
        if not save_buttons:
            save_buttons = await visible_items(frame.get_by_text("אשר", exact=True))
        if not save_buttons:
            save_buttons = await visible_items(frame.get_by_text("אישור", exact=True))
        if not save_buttons:
            raise RuntimeError("Note save button was not found")
        await save_buttons[-1].click()
        await asyncio.sleep(0.7)
        return True
    except Exception as exc:
        print(f"    [!] Could not add note: {exc}")
        return False


async def read_day_hours(frame, date_short: str) -> tuple | None:
    """קורא שעות כניסה/יציאה מיום. עובד גם במצב עריכה וגם במצב תצוגה."""
    try:
        day = await get_day(frame, date_short)

        # מצב עריכה — input fields
        hours = await visible_items(day.locator(SEL["hours_input"]))
        minutes = await visible_items(day.locator(SEL["minutes_input"]))
        if len(hours) >= 2 and len(minutes) >= 2:
            in_h  = (await hours[0].input_value()).strip()
            in_m  = (await minutes[0].input_value()).strip()
            out_h = (await hours[1].input_value()).strip()
            out_m = (await minutes[1].input_value()).strip()
            if in_h and out_h:
                entry = int(in_h) * 60 + int(in_m or 0)
                exit_ = int(out_h) * 60 + int(out_m or 0)
                if exit_ < entry:
                    exit_ += 24 * 60
                return entry, exit_

        # מצב תצוגה — מחפש HH:MM בטקסט של שורת היום
        text = await day.inner_text()
        times = re.findall(r'\b(\d{1,2}:\d{2})\b', text)
        if len(times) >= 2:
            entry = parse_hhmm(times[0])
            exit_ = parse_hhmm(times[1])
            if exit_ < entry:
                exit_ += 24 * 60
            return entry, exit_

        return None
    except Exception as exc:
        print(f"    [!] Could not read {date_short}: {exc}")
        return None


async def fill_day(frame, record: dict) -> bool:
    date_short = record["date"][:5]  # DD/MM  e.g. "05/04"
    print(f"\n[*] Processing {date_short} ({record['day']}) - {record['entry']} -> {record['exit']}")
    try:
        day = await get_day(frame, date_short)
    except Exception as exc:
        print(f"    [!] {exc}")
        return False

    if not await ensure_attendance_pair(frame, day):
        print(f"    [!] Could not create/find attendance inputs for {date_short}")
        return False

    in_hour, in_min = record["entry"].split(":", 1)
    out_hour, out_min = record["exit"].split(":", 1)

    hours = await visible_items(day.locator(SEL["hours_input"]))
    minutes = await visible_items(day.locator(SEL["minutes_input"]))
    if len(hours) < 2 or len(minutes) < 2:
        print(f"    [!] Visible time inputs were not found for {date_short}")
        return False

    print("    [i] Filling visible time inputs")
    await set_input_value(hours[0], in_hour)
    await set_input_value(minutes[0], in_min)
    await set_input_value(hours[1], out_hour)
    await set_input_value(minutes[1], out_min)
    await minutes[1].evaluate("el => el.blur()")
    await asyncio.sleep(0.5)
    return True


def duration_minutes(record: dict) -> int:
    in_hour, in_min = map(int, record["entry"].split(":", 1))
    out_hour, out_min = map(int, record["exit"].split(":", 1))
    start = in_hour * 60 + in_min
    end = out_hour * 60 + out_min
    if end < start:
        end += 24 * 60
    return end - start


def total_minutes(records: list[dict]) -> int:
    return sum(duration_minutes(record) for record in records)


def format_minutes(total: int) -> str:
    hours = total // 60
    minutes = total % 60
    return f"{hours:02d}:{minutes:02d}"


HEBREW_MONTHS = {
    "ינואר": "01", "פברואר": "02", "מרץ": "03", "אפריל": "04",
    "מאי": "05", "יוני": "06", "יולי": "07", "אוגוסט": "08",
    "ספטמבר": "09", "אוקטובר": "10", "נובמבר": "11", "דצמבר": "12",
}


EN_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


def parse_month_key(month_token: str, year: str) -> str | None:
    token = month_token.strip()
    if token in HEBREW_MONTHS:
        return f"{HEBREW_MONTHS[token]}/{year}"
    reversed_token = token[::-1]
    if reversed_token in HEBREW_MONTHS:
        return f"{HEBREW_MONTHS[reversed_token]}/{year}"
    if token.lower() in EN_MONTHS:
        return f"{EN_MONTHS[token.lower()]}/{year}"
    if reversed_token.lower() in EN_MONTHS:
        return f"{EN_MONTHS[reversed_token.lower()]}/{year}"

    m_numeric = re.fullmatch(r"(\d{1,2})", token)
    if m_numeric:
        mm = int(m_numeric.group(1))
        if 1 <= mm <= 12:
            return f"{mm:02d}/{year}"
    return None


def extract_pdf_text(pdf_path: str) -> str:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is not installed. Run: pip install -r requirements.txt")

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file was not found: {pdf_path}")

    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def parse_pdf_month_total(text: str) -> tuple[str, str]:

    # Supports both normal extraction and RTL-reversed extraction.
    month_match = re.search(r"לחודש\s+(\S+)\s+(\d{4})", text)
    if not month_match:
        month_match = re.search(r"(\d{4})\s+(\S+)\s+שדוחל", text)
    if not month_match:
        month_match = re.search(r"for\s+([A-Za-z]+)\s+(\d{4})", text, flags=re.IGNORECASE)
    month_key = None
    if month_match:
        if month_match.re.pattern.startswith("(\\d{4})"):
            month_key = parse_month_key(month_match.group(2), month_match.group(1))
        else:
            month_key = parse_month_key(month_match.group(1), month_match.group(2))

    # Fallback: infer month/year from attendance rows (DD/MM/YYYY) and pick most common.
    if not month_key:
        date_hits = re.findall(r"\b\d{2}/(\d{2})/(\d{4})\b", text)
        if date_hits:
            counts: dict[tuple[str, str], int] = {}
            for mm, yyyy in date_hits:
                counts[(mm, yyyy)] = counts.get((mm, yyyy), 0) + 1
            (mm, yyyy), _ = max(counts.items(), key=lambda item: item[1])
            month_key = f"{mm}/{yyyy}"

    if not month_key:
        raise ValueError("Could not find report month in PDF text")

    total_match = re.search(r"סה[\"׳״']?כ\s+נוכחות\s+חודשית\s+מדווחת[:\s]+(\d{1,3}:\d{2})", text)
    if not total_match:
        total_match = re.search(r"(\d{1,3}:\d{2})\s*:\s*תחוודמ\s+תישדוח\s+תוחכונ\s+כ[\"׳״']?הס", text)
    if not total_match:
        total_match = re.search(r"monthly\s+attendance\s+reported[:\s]+(\d{1,3}:\d{2})", text, flags=re.IGNORECASE)
    if not total_match:
        raise ValueError("Could not find monthly total hours in PDF text")

    return month_key, total_match.group(1)


def parse_pdf_attendance_rows(text: str) -> list[dict]:
    records: list[dict] = []
    seen_dates: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", line)
        if not date_match:
            continue

        date_value = date_match.group(1)
        times = re.findall(r"\b(\d{1,2}:\d{2})\b", line)
        if len(times) < 2:
            continue

        # In extracted lines, times typically appear as [daily_total, exit, entry].
        entry = times[-1]
        exit_ = times[-2]
        if date_value in seen_dates:
            continue
        seen_dates.add(date_value)

        records.append({
            "date": date_value,
            "day": "",
            "entry": f"{int(entry.split(':')[0]):02d}:{entry.split(':')[1]}",
            "exit": f"{int(exit_.split(':')[0]):02d}:{exit_.split(':')[1]}",
            "type": "",
            "notes": "",
        })

    records.sort(key=lambda r: tuple(map(int, r["date"].split("/")[::-1])))
    return records


def parse_pdf_report(pdf_path: str) -> tuple[str, str, list[dict]]:
    text = extract_pdf_text(pdf_path)
    month_key, total = parse_pdf_month_total(text)
    records = parse_pdf_attendance_rows(text)
    if not records:
        raise ValueError("Could not find attendance day rows in PDF text")
    return month_key, total, records


def parse_hhmm(s: str) -> int:
    """ממיר מחרוזת HH:MM למספר דקות."""
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def wait_for_user_close() -> None:
    """Avoid blocking in non-interactive flows such as the local web UI."""
    if NO_PAUSE:
        return
    if not sys.stdin or not sys.stdin.isatty():
        return
    input("  [Press Enter to close] ")


def is_interactive_console() -> bool:
    return bool((not NO_PAUSE) and sys.stdin and sys.stdin.isatty())


async def wait_for_manual_browser_close(context) -> None:
    print("  Browser will remain open. Close the browser window to finish.")
    while True:
        try:
            pages = context.pages
        except Exception:
            break
        if not pages:
            break
        if all(page.is_closed() for page in pages):
            break
        await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    global VERIFY_MONTH

    print("=" * 60)
    print("  Synerion Attendance Auto-Filler")
    print("=" * 60)

    if not PDF_PATH:
        print("[!] Missing required --pdf parameter")
        return

    try:
        default_month, pdf_total_str, all_pdf_records = parse_pdf_report(PDF_PATH)
        print(f"[*] Loaded PDF report: month={default_month}, total={pdf_total_str}")
        print(f"[*] Extracted attendance rows from PDF: {len(all_pdf_records)}")
    except Exception as exc:
        print(f"[!] Could not parse PDF report from --pdf: {exc}")
        return

    records_to_fill = all_pdf_records
    if ONLY_DATE:
        records_to_fill = [record for record in all_pdf_records if record["date"] == ONLY_DATE]
        print(f"[*] Filtered to {len(records_to_fill)} record(s) via --only-date={ONLY_DATE}")

    if not records_to_fill:
        print("[!] No attendance rows to process after filtering")
        return

    if SUMMARY_ONLY:
        calculated_total = total_minutes(records_to_fill)
        print("\n" + "=" * 60)
        print("  Summary-only mode (no website changes)")
        print(f"  Month:                   {default_month}")
        print("  Rows extracted from PDF:")
        for record in records_to_fill:
            print(f"    {record['date']}: {record['entry']} -> {record['exit']}")
        print(f"  Calculated total:        {format_minutes(calculated_total)}")
        print(f"  PDF total:               {pdf_total_str}")
        if calculated_total == parse_hhmm(pdf_total_str):
            print("  [OK] Full match - the data matches the PDF")
        else:
            delta = calculated_total - parse_hhmm(pdf_total_str)
            sign = "+" if delta >= 0 else "-"
            print(f"  [!] Mismatch - gap: {sign}{format_minutes(abs(delta))}")
        print("=" * 60)
        return

    if VERIFY_MODE:
        print("\nOpening browser for verification...\n")
        tmp_profile = tempfile.mkdtemp(prefix="synerion_chrome_")
        context = None
        try:
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=tmp_profile,
                    executable_path=BROWSER_EXECUTABLE,
                    headless=False,
                    slow_mo=200,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                page = context.pages[0] if context.pages else await context.new_page()

                print("[*] Opening login page - please sign in in the browser...")
                await page.goto(URL_BASE)
                await page.wait_for_load_state("networkidle")
                print("[*] Waiting for sign-in...")
                try:
                    await page.wait_for_url(lambda url: "Login" not in url and "login" not in url, timeout=120000)
                except PWTimeout:
                    print("[!] No sign-in detected within 120 seconds.")
                    return
                print("[OK] Sign-in detected")

                frame = await navigate_to_attendance(page)
                target_month = VERIFY_MONTH or default_month
                await navigate_to_month(frame, target_month)
                await ensure_edit_mode(frame)
                await asyncio.sleep(1.5)

                # --- קרא סיכום מהfooter של הדף ---
                print(f"\n[*] Reading Synerion totals for {target_month}...\n")

                async def read_footer_value(selector: str) -> str:
                    loc = frame.locator(selector)
                    if await loc.count():
                        return (await loc.first.inner_text()).strip()
                    return "N/A"

                regular_str  = await read_footer_value("#totalRegular")
                overtime_str = await read_footer_value("#totalOverTime")

                print(f"  Regular hours (#totalRegular):  {regular_str}")
                print(f"  Overtime (#totalOverTime):      {overtime_str}")

                # חשב סכום
                def safe_hhmm(s: str) -> int:
                    m = re.match(r'-?(\d+):(\d+)', s)
                    if not m:
                        return 0
                    val = int(m.group(1)) * 60 + int(m.group(2))
                    return -val if s.startswith("-") else val

                site_regular  = safe_hhmm(regular_str)
                site_overtime = safe_hhmm(overtime_str)
                site_total    = site_regular + site_overtime

                print(f"\n  Synerion total (regular + overtime): {format_minutes(site_regular)} + {format_minutes(site_overtime)} = {format_minutes(site_total)}")

                # Cancel edit mode without saving
                cancel_btn = frame.locator(SEL["cancel_button"])
                if await cancel_btn.count() and await cancel_btn.first.is_visible():
                    await cancel_btn.first.click()
                    await asyncio.sleep(1)

                pdf_total = parse_hhmm(pdf_total_str)
                print("\n" + "=" * 60)
                print(f"  Verification results - {target_month}")
                print(f"  Synerion total:           {format_minutes(site_total)}")
                print(f"  PDF total:                {pdf_total_str}")
                if site_total == pdf_total:
                    print("  [OK] Full match - website data matches the PDF")
                else:
                    delta = site_total - pdf_total
                    sign = "+" if delta >= 0 else "-"
                    print(f"  [!] Mismatch - gap: {sign}{format_minutes(abs(delta))}")
                print("=" * 60)

                if is_interactive_console():
                    print("\n  Browser is open for inspection. Press Enter here to close it when done.")
                else:
                    if KEEP_BROWSER_OPEN:
                        print("\n  Non-interactive run detected. Browser will stay open until you close it.")
                    else:
                        print("\n  Non-interactive run detected. Browser will close automatically.")
                wait_for_user_close()
                if KEEP_BROWSER_OPEN and not is_interactive_console():
                    await wait_for_manual_browser_close(context)
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            shutil.rmtree(tmp_profile, ignore_errors=True)
        return

    print("\nOpening browser...\n")

    # Use a clean temp profile to avoid accessing local Chrome secrets
    tmp_profile = tempfile.mkdtemp(prefix="synerion_chrome_")
    print(f"[*] Using isolated browser profile: {tmp_profile}\n")

    context = None
    try:
        async with async_playwright() as p:
            # Launch real Chrome with isolated profile
            context = await p.chromium.launch_persistent_context(
                user_data_dir=tmp_profile,
                executable_path=BROWSER_EXECUTABLE,
                headless=False,
                slow_mo=300,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else await context.new_page()

            # ---- Open login page and wait for manual login ----
            print("[*] Opening login page - please sign in in the browser...")
            await page.goto(URL_BASE)
            await page.wait_for_load_state("networkidle")
            # Wait until user logs in (URL changes away from /Login)
            print("[*] Waiting for sign-in... (sign in in the browser)")
            try:
                await page.wait_for_url(lambda url: "Login" not in url and "login" not in url, timeout=120000)
            except PWTimeout:
                print("[!] No sign-in detected within 120 seconds. Run again after signing in.")
                return
            print("[OK] Sign-in detected")

            # ---- Navigate to attendance ----
            frame = await navigate_to_attendance(page)

            # ---- Navigate to month extracted from PDF ----
            await navigate_to_month(frame, default_month)

            # ---- Switch to monthly edit mode ----
            await ensure_edit_mode(frame)

            # ---- Fill each day ----
            results = {"ok": 0, "failed": 0}
            successful_records = []
            for record in records_to_fill:
                success = await fill_day(frame, record)
                if success:
                    results["ok"] += 1
                    successful_records.append(record)
                else:
                    results["failed"] += 1

                if not AUTO_MODE:
                    print("    [i] AUTO disabled - continuing without pausing in iframe mode")

            if results["ok"]:
                print("\n[*] Saving monthly changes...")
                await frame.locator(SEL["save_button"]).click()
                await asyncio.sleep(3)
                print("[OK] Monthly save clicked")

            # ---- בדיקת סיכום מה-footer לאחר שמירה ----
            await asyncio.sleep(2)

            async def read_footer(sel: str) -> str:
                loc = frame.locator(sel)
                if await loc.count():
                    return (await loc.first.inner_text()).strip()
                return "N/A"

            regular_str  = await read_footer("#totalRegular")
            overtime_str = await read_footer("#totalOverTime")

            def safe_hhmm(s: str) -> int:
                m = re.match(r'-?(\d+):(\d+)', s)
                if not m:
                    return 0
                val = int(m.group(1)) * 60 + int(m.group(2))
                return -val if s.startswith("-") else val

            site_total = safe_hhmm(regular_str) + safe_hhmm(overtime_str)
            pdf_total = parse_hhmm(pdf_total_str)

            # ---- Summary ----
            print("\n" + "=" * 60)
            print(f"  Done: {results['ok']} days filled, {results['failed']} failed")
            print(f"  Month from PDF:          {default_month}")
            print(f"  Regular hours in site:   {regular_str}")
            print(f"  Overtime in site:        {overtime_str}")
            print(f"  Site total:              {format_minutes(site_total)}")
            print(f"  PDF total:               {pdf_total_str}")
            if site_total == pdf_total:
                print("  [OK] Full match - site data matches the PDF")
            else:
                delta = site_total - pdf_total
                sign = "+" if delta >= 0 else "-"
                print(f"  [!] Mismatch - gap: {sign}{format_minutes(abs(delta))}")
            print("=" * 60)

            if DEBUG_ARTIFACTS:
                await page.screenshot(path=SCREENSHOT_PATH)
                print(f"  Debug screenshot saved -> {SCREENSHOT_PATH}")

            if is_interactive_console():
                print("\n  Browser is open for inspection. Press Enter here to close it when done.")
            else:
                if KEEP_BROWSER_OPEN:
                    print("\n  Non-interactive run detected. Browser will stay open until you close it.")
                else:
                    print("\n  Non-interactive run detected. Browser will close automatically.")
            wait_for_user_close()
            if KEEP_BROWSER_OPEN and not is_interactive_console():
                await wait_for_manual_browser_close(context)
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        shutil.rmtree(tmp_profile, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
