"""
Scrapes electricity data from Dash IOT for a given site and date range.
Uses Playwright with headless=True for reliability on JS-heavy pages.
"""
import os
from playwright.sync_api import sync_playwright

DASH_URL = "https://www.dash-iot.com"
DEBUG_DIR = os.path.join(os.path.dirname(__file__), '..', 'debug_screenshots')

def _screenshot(page, name):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    path = os.path.join(DEBUG_DIR, f"{name}.png")
    page.screenshot(path=path)
    print(f"[Scraper] Screenshot: {path}")

def get_site_data(username, password, site_name, date_from, date_to):
    """
    Returns dict with totals and daily rows for a site + date range.
    site_name: name as shown in Dash IOT dropdown
    date_from / date_to: 'YYYY-MM-DD' strings
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # visible for debugging
        page = browser.new_page()

        # Login
        page.goto(f"{DASH_URL}/login")
        page.wait_for_load_state("networkidle")
        page.fill('input[type="text"]', username)
        page.fill('input[type="password"]', password)
        _screenshot(page, "1_login_filled")
        page.keyboard.press("Enter")
        page.wait_for_url(f"{DASH_URL}/index", timeout=20000)
        print("[Scraper] Logged in")

        # Navigate to electricity detail
        page.goto(f"{DASH_URL}/detail_electricity")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        _screenshot(page, "2_detail_page")

        # Get and select site
        options = page.evaluate("""
            () => Array.from(document.querySelector('#available_sites')?.options || [])
                .map(o => ({value: o.value, text: o.text.trim()}))
        """)
        print(f"[Scraper] Available sites: {options}")

        site_name_lower = site_name.lower().strip()
        matched = next((o for o in options if site_name_lower in o['text'].lower()), None)
        if not matched:
            raise Exception(f"Site '{site_name}' not found. Available: {[o['text'] for o in options]}")

        page.select_option('#available_sites', value=matched['value'])
        print(f"[Scraper] Selected: {matched['text']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Use React-compatible input setter for date fields
        page.evaluate(f"""
            () => {{
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                const inputs = document.querySelectorAll('input[type="date"]');
                if (inputs[0]) {{
                    setter.call(inputs[0], '{date_from}');
                    inputs[0].dispatchEvent(new Event('input', {{bubbles: true}}));
                    inputs[0].dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
                if (inputs[1]) {{
                    setter.call(inputs[1], '{date_to}');
                    inputs[1].dispatchEvent(new Event('input', {{bubbles: true}}));
                    inputs[1].dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
            }}
        """)
        page.wait_for_timeout(500)

        # Set Group By to Day using React-compatible select setter
        page.evaluate("""
            () => {
                const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
                const selects = document.querySelectorAll('select');
                for (const s of selects) {
                    const opts = Array.from(s.options).map(o => o.value.toLowerCase());
                    if (opts.includes('day')) {
                        setter.call(s, 'day');
                        s.dispatchEvent(new Event('input', {bubbles: true}));
                        s.dispatchEvent(new Event('change', {bubbles: true}));
                        break;
                    }
                }
            }
        """)
        page.wait_for_timeout(500)
        _screenshot(page, "3_filters_set")

        # Debug: dump all clickable elements
        clickables = page.evaluate("""
            () => {
                const els = document.querySelectorAll('button, input[type="submit"], a.btn, [type="submit"], .btn');
                return Array.from(els).map(e => ({
                    tag: e.tagName,
                    type: e.type || '',
                    text: e.innerText || e.value || '',
                    cls: e.className
                }));
            }
        """)
        print(f"[Scraper] Clickable elements: {clickables}")

        # Try multiple selectors for the filter button
        clicked = page.evaluate("""
            () => {
                const candidates = [
                    ...document.querySelectorAll('input[type="submit"]'),
                    ...document.querySelectorAll('button'),
                    ...document.querySelectorAll('[type="submit"]'),
                    ...document.querySelectorAll('a')
                ];
                const btn = candidates.find(el =>
                    /filter/i.test(el.innerText || el.value || el.textContent)
                );
                if (btn) {
                    btn.scrollIntoView();
                    btn.click();
                    return `${btn.tagName} - ${btn.innerText || btn.value}`;
                }
                return null;
            }
        """)
        print(f"[Scraper] Clicked: {clicked}")
        _screenshot(page, "3b_filter_button_visible")
        page.wait_for_load_state("networkidle", timeout=20000)
        page.wait_for_timeout(4000)
        _screenshot(page, "4_after_filter")

        # Check how many rows loaded
        row_count = page.evaluate("() => document.querySelectorAll('table tbody tr').length")
        print(f"[Scraper] Rows visible before page size change: {row_count}")

        # Set page size to 100
        changed = page.evaluate("""
            () => {
                const selects = document.querySelectorAll('select');
                for (const s of selects) {
                    const vals = Array.from(s.options).map(o => o.value);
                    if (vals.includes('100') || vals.includes('10')) {
                        const prev = s.value;
                        s.value = '100';
                        s.dispatchEvent(new Event('change', {bubbles: true}));
                        return `changed from ${prev} to 100`;
                    }
                }
                return 'no page-size select found';
            }
        """)
        print(f"[Scraper] Page size: {changed}")
        page.wait_for_timeout(3000)
        _screenshot(page, "5_after_pagesize")

        row_count2 = page.evaluate("() => document.querySelectorAll('table tbody tr').length")
        print(f"[Scraper] Rows after page size change: {row_count2}")

        # Scrape table
        data = page.evaluate("""
            () => {
                const rows = document.querySelectorAll('table tbody tr');
                const result = [];
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 4) {
                        result.push({
                            date: cells[0].innerText.trim(),
                            consumption: parseFloat(cells[1].innerText.replace(/,/g,'').trim()) || 0,
                            production: parseFloat(cells[2].innerText.replace(/,/g,'').trim()) || 0,
                            grid_import: parseFloat(cells[3].innerText.replace(/,/g,'').trim()) || 0,
                            grid_export: cells[4] ? (parseFloat(cells[4].innerText.replace(/,/g,'').trim()) || 0) : 0,
                        });
                    }
                });
                return result;
            }
        """)

        print(f"[Scraper] Scraped {len(data)} rows. First 3: {data[:3]}")
        _screenshot(page, "6_final_table")
        browser.close()

    if not data:
        return None

    totals = {
        "consumption": round(sum(r["consumption"] for r in data), 2),
        "production": round(sum(r["production"] for r in data), 2),
        "grid_import": round(sum(r["grid_import"] for r in data), 2),
        "grid_export": round(sum(r["grid_export"] for r in data), 2),
    }
    totals["self_consumed"] = round(totals["production"] - totals["grid_export"], 2)

    return {"rows": data, "totals": totals}
