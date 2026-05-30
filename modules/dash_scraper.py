from playwright.sync_api import sync_playwright
import os, time

DEBUG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'debug_screenshots')

def _ss(page, name):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    page.screenshot(path=os.path.join(DEBUG_DIR, f'{name}.png'))

def _fuzzy_match(site_name, option_text):
    """Return True if any significant word of site_name appears in option_text."""
    site_words = [w.strip() for w in site_name.lower().replace('/', ' ').split() if len(w) > 2]
    opt = option_text.lower()
    return any(w in opt for w in site_words)

def get_site_data(username, password, site_name, date_from, date_to):
    """
    Scrape Dash IOT for a given site and date range.
    Returns list of rows (lists of cell values) from the data table.
    """
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            # Login
            page.goto('https://monitoring.dashiot.co.za/login', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            _ss(page, '1_login_page')

            page.fill('input[type="email"], input[name="email"], input[name="username"]', username)
            page.fill('input[type="password"]', password)
            _ss(page, '2_filled_login')
            page.keyboard.press('Enter')
            page.wait_for_load_state('networkidle', timeout=15000)
            _ss(page, '3_after_login')

            # Navigate to energy/reporting section
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
            page.wait_for_timeout(3000)

            # Select site - exact match first, then fuzzy
            try:
                selects = page.locator('select').all()
                for sel in selects:
                    options = sel.locator('option').all()
                    matched = False
                    for opt in options:
                        opt_text = opt.inner_text()
                        if site_name.lower() in opt_text.lower() or opt_text.lower() in site_name.lower():
                            sel.select_option(value=opt.get_attribute('value'))
                            page.wait_for_timeout(1000)
                            matched = True
                            print(f'Site matched (exact): {opt_text}')
                            break
                    if not matched:
                        for opt in options:
                            opt_text = opt.inner_text()
                            if _fuzzy_match(site_name, opt_text):
                                sel.select_option(value=opt.get_attribute('value'))
                                page.wait_for_timeout(1000)
                                matched = True
                                print(f'Site matched (fuzzy): {opt_text}')
                                break
                    if matched:
                        break
            except Exception as e:
                print(f'Site selection warning: {e}')

            _ss(page, '5_after_site_select')

            # Set dates using React-compatible setter
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

            for sel in ['input[name="dateFrom"]', 'input[placeholder*="from" i]',
                        'input[id*="from" i]', 'input[type="date"]:first-of-type']:
                try:
                    set_date_input(sel, date_from)
                    break
                except:
                    pass

            for sel in ['input[name="dateTo"]', 'input[placeholder*="to" i]',
                        'input[id*="to" i]', 'input[type="date"]:last-of-type']:
                try:
                    set_date_input(sel, date_to)
                    break
                except:
                    pass

            _ss(page, '6_dates_set')

            # Set page size to max
            try:
                page.evaluate("""
                    (function() {
                        var selects = document.querySelectorAll('select');
                        for (var s of selects) {
                            var opts = Array.from(s.options).map(o => o.value);
                            if (opts.includes('100')) {
                                s.value = '100';
                                s.dispatchEvent(new Event('change', {bubbles:true}));
                                break;
                            }
                        }
                    })();
                """)
            except:
                pass

            # Click filter/apply button
            try:
                page.evaluate("""
                    (function() {
                        var all = Array.from(document.querySelectorAll('button, input[type=submit], input[type=button]'));
                        for (var el of all) {
                            var txt = (el.innerText || el.value || '').toLowerCase();
                            if (txt.includes('filter') || txt.includes('search') || txt.includes('apply') || txt.includes('go')) {
                                el.scrollIntoView();
                                el.click();
                                break;
                            }
                        }
                    })();
                """)
                page.wait_for_timeout(4000)
            except Exception as e:
                print(f'Filter click warning: {e}')

            _ss(page, '7_after_filter')

            # Extract table data
            page.wait_for_timeout(2000)
            rows = page.locator('table tbody tr').all()
            for row in rows:
                cells = [td.inner_text().strip() for td in row.locator('td').all()]
                if cells and len(cells) >= 2:
                    results.append(cells)

            print(f'Scraped {len(results)} rows for site "{site_name}"')
            _ss(page, '8_data_extracted')

        except Exception as e:
            print(f'Scraper error: {e}')
            _ss(page, 'error_state')
        finally:
            browser.close()

    return results
