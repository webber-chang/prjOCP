import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import re
import time
import urllib.parse
import urllib.request
import requests
import json
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =====================================================
ACCOUNT_EMAIL    = "gmcwb05@gmail.com"
ACCOUNT_PASSWORD = "Luigi0522@"
LOGIN_URL = "https://skillcertpro.com/my-account/"
EXAM_URL  = "https://skillcertpro.com/oracle-database-administration-i-1z0-082-exam-dumps/"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_HTML = os.path.join(BASE_DIR, "Oracle_1Z0_082_Full.html")
DATA_JSON   = os.path.join(BASE_DIR, "exam_data.json")
IMAGES_DIR  = os.path.join(BASE_DIR, "images")
MAX_QUESTIONS = 500
# =====================================================

os.makedirs(IMAGES_DIR, exist_ok=True)

target_input = input("請輸入要單獨重抓的 Mock Exam 數字 (例如 7)，或直接按 Enter 抓取全部：").strip()
target_exam_num = int(target_input) if target_input.isdigit() else None

options = uc.ChromeOptions()
options.add_argument("--window-size=1280,900")
driver = uc.Chrome(options=options, version_main=151)
driver.set_window_size(1280, 900)
wait = WebDriverWait(driver, 20)


# ── 圖片下載並轉為本地路徑 ────────────────────────────
def download_image(img_url, exam_num, q_num, img_idx):
    """下載圖片到 images/ 資料夾，回傳本地相對路徑"""
    try:
        ext = os.path.splitext(urllib.parse.urlparse(img_url).path)[1]
        if not ext or ext.lower() not in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
            ext = '.png'
        filename = f"E{exam_num:02d}_Q{q_num:03d}_img{img_idx}{ext}"
        local_path = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(local_path):
            cookies = driver.get_cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': EXAM_URL,
            }
            res = requests.get(img_url, cookies=cookie_dict, headers=headers, stream=True)
            if res.status_code == 200:
                with open(local_path, 'wb') as f:
                    for chunk in res.iter_content(1024):
                        f.write(chunk)
            else:
                raise Exception(f"HTTP {res.status_code}")
        return local_path.replace("\\", "/")
    except Exception as e:
        print(f"    [!] 圖片下載失敗 {img_url}: {e}")
        return img_url


def process_html_images(html_content, exam_num, q_num):
    """把 HTML 內的 <img src="..."> 換成本地路徑"""
    img_pattern = re.compile(r'<img([^>]*?)src=["\']([^"\']+)["\']([^>]*?)>', re.IGNORECASE)
    img_idx = [0]

    def replace_img(m):
        img_idx[0] += 1
        before, url, after = m.group(1), m.group(2), m.group(3)
        if url.startswith('data:'):
            return m.group(0)
        local_path = download_image(url, exam_num, q_num, img_idx[0])
        return f'<img{before}src="{local_path}"{after}>'

    return img_pattern.sub(replace_img, html_content)


# ── 取得可見題目文字（去重用）────────────────────────
def get_visible_question_text():
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, ".wpProQuiz_question_text")
        for e in elems:
            if e.is_displayed():
                return e.text.strip()[:80]
    except Exception:
        pass
    return None


# ── 取得可見題目完整 HTML ─────────────────────────────
def get_visible_question_html():
    try:
        items = driver.find_elements(By.CSS_SELECTOR, ".wpProQuiz_listItem")
        for item in items:
            style = item.get_attribute("style") or ""
            if "display: none" in style or "display:none" in style:
                continue
            if item.is_displayed():
                return item.get_attribute("innerHTML")
    except Exception:
        pass
    return None


# ── 點 Check 並取得答案說明 HTML ─────────────────────
def click_check_and_get_answer():
    try:
        for sel in ["input[name='check']", "input[value='Check']", "button[name='check']",
                    ".wpProQuiz_button_check", "input.wpProQuiz_button"]:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            for btn in btns:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1.5)
                    break

        answer_html = ""
        for sel in [".wpProQuiz_response", ".wpProQuiz_correct", ".wpProQuiz_incorrect",
                    ".wpProQuiz_tip", ".wpProQuiz_answerMessage"]:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for e in elems:
                if e.is_displayed():
                    answer_html += e.get_attribute("outerHTML") + "\n"

        correct_items = driver.find_elements(By.CSS_SELECTOR,
            ".wpProQuiz_answerCorrect, .wpProQuiz_correct, li.correct, li.wpProQuiz_answerCorrect")
        for ci in correct_items:
            if ci.is_displayed():
                answer_html += f'<div class="correct-answer-highlight">{ci.get_attribute("outerHTML")}</div>\n'

        return answer_html if answer_html else "<p><em>（未能取得答案）</em></p>"
    except Exception as e:
        return f"<p><em>（取答案失敗：{e}）</em></p>"


# ── 捲動到題目 ────────────────────────────────────────
def scroll_to_question():
    try:
        elem = driver.find_element(By.CSS_SELECTOR,
            ".wpProQuiz_listItem:not([style*='display: none']):not([style*='display:none'])")
        driver.execute_script("arguments[0].scrollIntoView({block:'start'});", elem)
        time.sleep(0.3)
    except Exception:
        driver.execute_script("window.scrollTo(0, 0);")


# ── 點 Next ───────────────────────────────────────────
def click_next_js():
    for sel in ["input[name='next']", "input[value='Next']", "button[name='next']"]:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            for btn in btns:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    return True
        except Exception:
            pass
    return False


# ── 取得所有 Mock Exam 頁面 URL ───────────────────────
def get_exam_page_urls():
    """
    從頁面底部的分頁連結取得所有 Mock Exam URL。
    例如 Pages: 1 2 3 4 5 6 7 8
    回傳 list of dict {exam_num, url}
    """
    urls = []
    try:
        page_links = driver.find_elements(By.CSS_SELECTOR,
            ".page-numbers a, .pagination a, nav.pagination a, a.page-numbers")
        seen_urls = set()
        for link in page_links:
            href = link.get_attribute("href") or ""
            text = link.text.strip()
            if href and href not in seen_urls and text.isdigit():
                seen_urls.add(href)
                urls.append((int(text), href))
        urls.sort(key=lambda x: x[0])
    except Exception as e:
        print(f"  [!] 自動偵測分頁失敗：{e}")

    # 確保第 1 頁（目前頁）也在清單裡
    if not any(n == 1 for n, _ in urls):
        urls.insert(0, (1, EXAM_URL))

    if len(urls) <= 1:
        # fallback：手動建立 8 個頁面 URL（WordPress 常見格式）
        base = EXAM_URL.rstrip("/")
        urls = [(1, EXAM_URL)]
        for i in range(2, 9):
            urls.append((i, f"{base}/{i}/"))

    print(f"  [偵測到 {len(urls)} 個 Mock Exam 頁面]")
    for n, u in urls:
        print(f"    Mock Exam {n}: {u}")
    return urls


# ── 點擊 Start Test ───────────────────────────────────
def click_start_test():
    for sel in [
        "input[name='startQuiz']",
        "input[value='Start Test']",
        "input[value='Start Quiz']",
        ".wpProQuiz_button",
    ]:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", btn)
            print(f"  [OK] 點擊 Start（{sel}）")
            time.sleep(4)
            return True
        except Exception:
            pass
    return False


# ── 抓取單一 Mock Exam 的所有題目 ─────────────────────
def scrape_exam(exam_num, exam_url, exam_data):
    """前往指定 Mock Exam 頁面，抓取所有題目，直接存入 exam_data"""
    print(f"\n{'='*55}")
    print(f"  Mock Exam {exam_num}：{exam_url}")
    print(f"{'='*55}")

    exam_entry = {
        "exam_num": exam_num,
        "label": f"Mock Exam {exam_num}",
        "url": exam_url,
        "questions": []
    }
    exam_data.append(exam_entry)

    max_retries = 3
    seen = set()

    for attempt in range(max_retries):
        try:
            driver.get(exam_url)
            time.sleep(5)

            if not click_start_test():
                debug_file = f"debug_exam{exam_num}.html"
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                print(f"  [!] 找不到 Start Test，已存 {debug_file}，略過此頁")
                return

            q_num = len(exam_entry["questions"])
            if q_num > 0:
                print(f"    [恢復進度] 正在快轉前 {q_num} 題，請稍候...")
                for _ in range(q_num):
                    click_next_js()
                    time.sleep(0.3)
                    
            consecutive_same = 0
            last_q_preview = None

            while q_num < MAX_QUESTIONS:
                time.sleep(1)
                scroll_to_question()
                time.sleep(0.5)

                q_preview = get_visible_question_text()

                if q_preview is None:
                    print(f"    [!] 看不到題目（已抓 {q_num} 題），嘗試繼續...")
                    if not click_next_js():
                        print("    [END] 無法點 Next，結束此 Exam")
                        break
                    continue

                if last_q_preview and q_preview == last_q_preview:
                    consecutive_same += 1
                    if consecutive_same >= 2:
                        print(f"    [END] 畫面未切換（可能已到底部），結束（共 {q_num} 題）")
                        break
                    print("    [!] 題目尚未切換，稍候重試...")
                    time.sleep(1)
                    continue
                else:
                    consecutive_same = 0
                    last_q_preview = q_preview
                    q_num += 1

                    # 抓題目 HTML + 處理圖片
                    q_html = get_visible_question_html() or "<p>（無法取得題目內容）</p>"
                    q_html = process_html_images(q_html, exam_num, q_num)

                    # 點 Check 取答案
                    answer_html = click_check_and_get_answer()
                    answer_html = process_html_images(answer_html, exam_num, q_num)

                    exam_entry["questions"].append({
                        "exam_num": exam_num,
                        "q_num": q_num,
                        "preview": q_preview,
                        "question_html": q_html,
                        "answer_html": answer_html,
                    })
                    print(f"    [OK] Q{q_num} 已抓取  [{q_preview[:45]}]")

                if not click_next_js():
                    print(f"    [END] 找不到 Next，結束（共 {q_num} 題）")
                    break

            print(f"  → Mock Exam {exam_num} 完成，共 {q_num} 題")
            return

        except Exception as e:
            print(f"    [!] 抓取時發生錯誤：{e}")
            if attempt < max_retries - 1:
                print(f"    [!] 準備進行第 {attempt + 2}/{max_retries} 次重試...")
            else:
                print(f"    [!] 重試達上限，放棄此回，保留已抓取的 {len(exam_entry['questions'])} 題。")
                return


# ── HTML 樣式 ─────────────────────────────────────────
HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Oracle 1Z0-082 完整題庫（8 Mock Exams）</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #f0f2f5;
    color: #1a1a2e;
    padding: 20px;
    max-width: 1100px;
    margin: 0 auto;
  }
  h1 {
    text-align: center;
    font-size: 1.9em;
    color: #c0392b;
    margin: 20px 0 6px;
    padding-bottom: 12px;
    border-bottom: 3px solid #c0392b;
  }
  .subtitle {
    text-align: center;
    color: #888;
    font-size: 0.9em;
    margin-bottom: 30px;
  }

  /* ── Exam 章節標題 ── */
  .exam-section { margin-bottom: 40px; }
  .exam-title {
    display: flex;
    align-items: center;
    gap: 12px;
    background: linear-gradient(90deg, #1a1a2e, #2c3e7a);
    color: #fff;
    padding: 14px 24px;
    border-radius: 10px 10px 0 0;
    font-size: 1.25em;
    font-weight: bold;
    margin-bottom: 2px;
  }
  .exam-title .badge {
    background: #e74c3c;
    border-radius: 20px;
    padding: 2px 12px;
    font-size: 0.8em;
    font-weight: normal;
  }

  /* ── 題目卡片 ── */
  .question-block {
    background: #fff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
    margin-bottom: 3px;
    overflow: hidden;
    border-left: 4px solid #e0e0e0;
    transition: border-color 0.2s;
  }
  .question-block:last-child {
    border-radius: 0 0 10px 10px;
    margin-bottom: 0;
  }
  .question-block:hover { border-left-color: #c0392b; }
  .question-header {
    background: #f7f7f7;
    color: #c0392b;
    padding: 10px 18px;
    font-size: 0.95em;
    font-weight: bold;
    border-bottom: 1px solid #eee;
  }
  .question-body {
    padding: 16px 20px;
    line-height: 1.7;
  }
  .question-body img {
    max-width: 100%;
    border: 1px solid #ddd;
    border-radius: 6px;
    margin: 10px 0;
    display: block;
  }
  .question-body pre, .question-body code {
    background: #f4f4f4;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 10px 14px;
    font-family: 'Courier New', monospace;
    font-size: 0.9em;
    overflow-x: auto;
    white-space: pre;
    display: block;
    margin: 10px 0;
  }
  .options-list { list-style: none; margin-top: 12px; }
  .options-list li {
    padding: 9px 14px;
    margin: 5px 0;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    background: #fafafa;
  }

  /* ── 折疊答案 ── */
  details.answer-section { border-top: 2px dashed #e8e8e8; }
  details.answer-section summary {
    cursor: pointer;
    padding: 9px 18px;
    background: #eaf4fb;
    color: #2471a3;
    font-weight: bold;
    user-select: none;
    list-style: none;
    font-size: 0.9em;
  }
  details.answer-section summary::-webkit-details-marker { display: none; }
  details.answer-section summary::before { content: "▶ "; }
  details.answer-section[open] summary::before { content: "▼ "; }
  .answer-content {
    padding: 14px 20px;
    background: #f9fbfd;
    border-top: 1px solid #d6eaf8;
  }
  .answer-content .wpProQuiz_answerCorrect,
  .answer-content .correct-answer-highlight,
  .answer-content li.correct {
    background: #d5f5e3 !important;
    border-color: #2ecc71 !important;
    font-weight: bold;
  }

  /* ── TOC ── */
  .toc {
    background: #fff;
    border-radius: 10px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
    padding: 20px 24px;
    margin-bottom: 30px;
  }
  .toc > h2 { color: #1a1a2e; margin-bottom: 16px; font-size: 1.1em; }
  .toc-exam-group { margin-bottom: 14px; }
  .toc-exam-label {
    font-weight: bold;
    color: #c0392b;
    font-size: 0.9em;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .toc-exam-label a { color: inherit; text-decoration: none; }
  .toc-exam-label a:hover { text-decoration: underline; }
  .toc-grid { display: flex; flex-wrap: wrap; gap: 6px; margin-left: 4px; }
  .toc-grid a {
    padding: 3px 9px;
    background: #fdecea;
    color: #c0392b;
    border-radius: 16px;
    text-decoration: none;
    font-size: 0.82em;
    border: 1px solid #f5b7b1;
    transition: background 0.18s;
  }
  .toc-grid a:hover { background: #c0392b; color: #fff; }
  .back-top {
    display: block;
    text-align: right;
    padding: 5px 18px;
    font-size: 0.8em;
    color: #bbb;
    text-decoration: none;
  }
  .back-top:hover { color: #c0392b; }
  #toc-anchor { display: block; }
  .stats { text-align: center; color: #999; font-size: 0.85em; margin: 10px 0 24px; }
  .exam-stats { font-size: 0.82em; color: #aaa; font-weight: normal; margin-left: auto; }

  /* ── 懸浮列印控制選單 ── */
  .print-controls {
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: white;
    padding: 12px;
    border-radius: 8px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.15);
    display: flex;
    flex-direction: column;
    gap: 8px;
    z-index: 1000;
  }
  .print-controls button {
    background: #f8f9f9;
    border: 1px solid #d5dbdb;
    padding: 8px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9em;
    font-weight: bold;
    color: #2c3e50;
    transition: 0.2s;
    text-align: left;
  }
  .print-controls button:hover { background: #eaf2f8; border-color: #aed6f1; }

  /* ── 列印專用樣式 ── */
  @media print {
    .print-controls, .toc, .back-top, .stats { display: none !important; }
    body { background: white; padding: 0; }
    .question-block {
      box-shadow: none;
      border: 1px solid #ddd;
      page-break-inside: avoid;
    }
    .hide-answers-on-print details.answer-section {
      display: none !important;
    }
  }
</style>
</head>
<body>
<div class="print-controls">
  <button onclick="document.querySelectorAll('details').forEach(e => e.open = true)">📖 展開所有答案</button>
  <button onclick="document.querySelectorAll('details').forEach(e => e.open = false)">📕 折疊所有答案</button>
  <button onclick="document.body.classList.add('hide-answers-on-print'); window.print();">🖨️ 列印 (隱藏答案)</button>
  <button onclick="document.body.classList.remove('hide-answers-on-print'); document.querySelectorAll('details').forEach(e => e.open = true); window.print();">🖨️ 列印 (顯示答案)</button>
</div>
<span id="toc-anchor"></span>
<h1>🎓 Oracle 1Z0-082 完整題庫</h1>
<p class="subtitle">8 Mock Exams · 含答案與解析</p>
"""

HTML_TAIL = '\n<p class="stats">— 完整題庫結束 —</p>\n</body></html>'


# ══════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════
def load_data():
    if os.path.exists(DATA_JSON):
        try:
            with open(DATA_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] 讀取 {DATA_JSON} 失敗：{e}")
    return []

def save_data(data):
    try:
        with open(DATA_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  [+] 資料已存檔至 {DATA_JSON}")
    except Exception as e:
        print(f"[!] 存檔失敗：{e}")

exam_data = load_data()

try:
    # ── 登入 ──────────────────────────────────────────
    print("正在開啟登入頁...")
    driver.get(LOGIN_URL)
    time.sleep(4)

    if "logout" in driver.page_source.lower():
        print("偵測到已登入！")
    else:
        print("填入帳號密碼...")
        wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(ACCOUNT_EMAIL)
        driver.find_element(By.ID, "password").send_keys(ACCOUNT_PASSWORD)
        driver.find_element(By.NAME, "login").click()
        time.sleep(4)
        if "logout" in driver.page_source.lower():
            print("[OK] 登入成功！")
        else:
            raise SystemExit("[!] 登入失敗，請確認帳號密碼")

    # ── 前往主題目頁，偵測所有 Mock Exam 頁面 ────────
    print("\n前往主題目頁，偵測所有 Mock Exam 頁面...")
    driver.get(EXAM_URL)
    time.sleep(5)

    exam_pages = get_exam_page_urls()

    # ── 逐頁抓取 ──────────────────────────────────────
    for exam_num, exam_url in exam_pages:
        if target_exam_num is not None and exam_num != target_exam_num:
            continue  # 若有指定要抓的 Exam，則跳過其他的

        try:
            # 在 exam_data 中找到並移除舊的該回資料（若有的話）
            exam_data = [e for e in exam_data if e.get("exam_num") != exam_num]
            
            # 用一個暫存的 list 來接爬蟲結果，爬完再合併
            temp_list = []
            scrape_exam(exam_num, exam_url, temp_list)
            
            if temp_list:
                exam_data.append(temp_list[0])
                # 按照 exam_num 排序一下
                exam_data.sort(key=lambda x: x.get("exam_num", 0))
                # 每次抓完一個 Exam 就存檔一次，避免中斷全失
                save_data(exam_data)
                
        except Exception as e:
            print(f"  [!] 第 {exam_num} 回抓取時發生非預期錯誤：{e}。跳過此回，繼續下一回。")

    total_q = sum(len(e.get("questions", [])) for e in exam_data)
    print(f"\n[DONE] 全部完成！目前庫存共 {len(exam_data)} 個 Mock Exam，{total_q} 題")
    print("開始寫出 HTML...")

except KeyboardInterrupt:
    print("\n[!] 使用者手動中斷程式。準備將目前已抓取的進度儲存為 HTML...")
except Exception as e:
    print(f"\n[!] 發生錯誤：{e}。準備將目前已抓取的進度儲存為 HTML...")
finally:
    try:
        driver.quit()
    except Exception:
        pass

# ── 寫出各別的 HTML 檔 ────────────────────────────────
print("\n開始寫出各別的 HTML 檔...")

for exam in exam_data:
    en = exam["exam_num"]
    total_q_exam = len(exam["questions"])
    output_filename = os.path.join(BASE_DIR, f"Oracle_1Z0_082_MockExam_{en}.html")
    
    with open(output_filename, "w", encoding="utf-8") as f:
        # 修改 Head 的標題
        head_custom = HTML_HEAD.replace("完整題庫（8 Mock Exams）", f"Mock Exam {en}")
        head_custom = head_custom.replace("<h1>🎓 Oracle 1Z0-082 完整題庫</h1>", f"<h1>🎓 Oracle 1Z0-082 - Mock Exam {en}</h1>")
        head_custom = head_custom.replace('<p class="subtitle">8 Mock Exams · 含答案與解析</p>', f'<p class="subtitle">共 {total_q_exam} 題 · 含答案與解析</p>')
        
        f.write(head_custom)
        f.write(f'<p class="stats">Mock Exam {en} · {total_q_exam} 題 · 圖片存於 {IMAGES_DIR}/</p>\n')
        
        # ── TOC ──
        f.write('<div class="toc"><h2>📋 題目索引</h2>\n')
        f.write('<div class="toc-grid">')
        for qd in exam["questions"]:
            f.write(f'<a href="#e{en}q{qd["q_num"]}">Q{qd["q_num"]}</a>')
        f.write('</div>\n</div>\n')

        # ── Mock Exam 區塊 ──
        f.write(f'''
<div class="exam-section" id="exam{en}">
  <div class="exam-title">
    📝 Mock Exam {en}
    <span class="badge">{total_q_exam} 題</span>
    <span class="exam-stats" style="margin-left:auto;color:#aaa;font-size:0.78em;">{exam["url"]}</span>
  </div>
''')
        for qd in exam["questions"]:
            qn = qd["q_num"]
            f.write(f'''
  <div class="question-block" id="e{en}q{qn}">
    <div class="question-header">Question {qn}</div>
    <div class="question-body">
      {qd["question_html"]}
    </div>
    <details class="answer-section">
      <summary>查看答案與解析</summary>
      <div class="answer-content">
        {qd["answer_html"]}
      </div>
    </details>
    <a class="back-top" href="#toc-anchor">▲ 回頂端</a>
  </div>
''')
        f.write('</div>\n')  # end exam-section
        f.write(HTML_TAIL)
    
    print(f"  [+] 產出: Oracle_1Z0_082_MockExam_{en}.html")

print(f"\n[DONE] 所有 HTML 已輸出完畢！")
print(f"       圖片存於 ./{IMAGES_DIR}/ 資料夾")