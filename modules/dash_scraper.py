from playwright.sync_api import sync_playwright
import os, time

DEBUG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'debug_screenshots')

def _ss(page, name):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    page.screenshot(path=os.path.join(DEBUG_DIR, f'{name}.png'))

def get_site_data(username, password, site_name, date_from, date_to):
    """
    Scrape Dash IOT for a given site and date range.
    Returns list of dicts with keys: date, export_kwh, import_kwh, generation_kwh, consumption_kwh
    """
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            # --- LOGIN ---
            page.goto('https://monitoring.dashiot.co.za/login', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            _ss(page, '1_login_page')

            page.fill('input[type="email"], input[name="email"], input[name="username"]', username)
            page.fill('input[type="password"]', password)
            _ss(page, '2_filled_login')
            page.keyboard.press('Enter')
            page.wait_for_load_state('networkidle', timeout=15000)
            _ss(page, '3_after_login')

            # --- NAVIGATE TO ENERGY / FILTER PAGE ---
            # Try to find a link or menu item for energy/reporting
            for nav_text in ['Energy', 'Reports', 'Analytics', 'Overview']:
                try:
                    link = page.locator(f'a:has-text("{nav_text}"), button:has-text("{nav_text}")').first
                    if link.is_visible(timeout=2000):
                        link.click()
                        page.wait_for_load_state('networkidle', timeout=10000)
                        break
                except:
                    pass

            _ss(page, '4_after_nav')

            # --- SELECT SITE ---
            page.wait_for_timeout(3000)
            try:
                # Find site/location dropdown
                selects = page.locator('select').all()
                for sel in selects:
                    options = sel.locator('option').all()
                    for opt in options:
                        opt_text = opt.inner_text()
                        if site_name.lower() in opt_text.lower():
                            opt_val = opt.get_attribute('value')
                            sel.select_option(value=opt_val)
                            page.wait_for_timeout(1000)
                            break
            except Exception as e:
                print(f'Site selection warning: {e}')
            _ss(page, '5_after_site_select')

            # --- SET DATES using React-compatible setter ---
            def set_date_input(selector, value):
                page.wait_for_selector(selector, timeout=5000)
                page.evaluate(f"""
                    (function() {{
                        var el = document.querySelector('{selector}');
                        if (!el) return;
                        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(el, '{value}');
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }})();
                """)

            date_selectors_from = ['input[name="dateFrom"]', 'input[placeholder*="from" i]',
                                    'input[id*="from" i]', 'input[type="date"]:first-of-type']
            date_selectors_to   = ['input[name="dateTo"]', 'input[placeholder*="to" i]',
                                    'input[id*="to" i]', 'input[type="date"]:last-of-type']

            for sel in date_selectors_from:
                try:
                    set_date_input(sel, date_from)
                    break
                except:
                    pass
            for sel in date_selectors_to:
                try:
                    set_date_input(sel, date_to)
                    break
                except:
                    pass

            _ss(page, '6_dates_set')

            # --- SET PAGE SIZE TO 100 ---
            try:
                page.evaluate("""
                    (function() {
                        var selects = document.querySelectorAll('select');
                        for (var s of selects) {
                            var opts = Array.from(s.options).map(o => o.value);
                            if (opts.includes('100') || opts.includes('10')) {
                                s.value = opts.includes('100') ? '100' : opts[opts.length-1];
                                s.dispatchEvent(new Event('change', {bubbles:true}));
                                break;
                            }
                        }
                    })();
                """)
            except:
                pass

            # --- CLICK FILTER ---
            try:
                page.evaluate("""
                    (function() {
                        var all = Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], a'));
                        for (var el of all) {
                            var txt = (el.innerText || el.value || '').toLowerCase();
                            if (txt.includes('filter') || txt.includes('search') || txt.includes('apply')) {
                                el.scrollIntoView();
                                el.click();
                                break;
                            }
                        }
                    })();
                """)
                page.wait_for_timeout(3000)
            except Exception as e:
                print(f'Filter click warning: {e}')

            _ss(page, '7_after_filter')

            # --- EXTRACT TABLE DATA ---
            page.wait_for_timeout(2000)
            rows = page.locator('table tbody tr').all()
            for row in rows:
                cells = [td.inner_text().strip() for td in row.locator('td').all()]
                if cells and len(cells) >= 2:
                    results.append(cells)

            _ss(page, '8_data_extracted')

        except Exception as e:
            print(f'Scraper error: {e}')
            _ss(page, 'error_state')
        finally:
            browser.close()

    return results
