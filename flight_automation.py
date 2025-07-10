import asyncio
import re
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.async_api import async_playwright
import pandas as pd
from datetime import timedelta

# --- USER SETTINGS ---

# 1. Flight Search Parameters
DEPARTURE_CITY = "İstanbul Tümü"
ARRIVAL_CITY = "Tiran"
DEPARTURE_PORT_CODE = "IST_SAW"
ARRIVAL_PORT_CODE = "TIA"
TRIP_DURATIONS = [6, 7, 8]

# 2. File Names
DEPARTURE_CSV_FILE = 'departure_prices.csv'
RETURN_CSV_FILE = 'return_prices.csv'
ARCHIVE_CSV_FILE = 'previous_results.csv'

# 3. EMAIL SETTINGS
# IMPORTANT: For security, use a 16-digit "App Password" from Google, NOT your real password.
SENDER_EMAIL = "denemecan33@gmail.com"
RECIPIENT_EMAILS = ["asrnsevim@hotmail.com"]
# The password is read securely from GitHub Actions Secrets.
# It uses the provided password as a fallback if the secret is not found (for local testing).
EMAIL_PASSWORD = os.getenv('MAIL_SIFRESI')

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# ==============================================================================
# PART 1: WEB SCRAPING & DATA CLEANING
# ==============================================================================

def clean_and_parse_scraped_data(date_str_raw, price_str_raw):
    """
    Cleans, parses, and standardizes the raw data from the scraper at the source.
    """
    # Clean the price (e.g., "2.972 TL" -> 2972)
    price_int = int(re.sub(r'[\. TL]', '', price_str_raw))

    # This dictionary MUST remain Turkish as the source data from the website is in Turkish.
    turkish_to_english_months = {
        'Ocak': 'January', 'Şubat': 'February', 'Mart': 'March', 'Nisan': 'April', 'Mayıs': 'May',
        'Haziran': 'June', 'Temmuz': 'July', 'Ağustos': 'August', 'Eylül': 'September',
        'Ekim': 'October', 'Kasım': 'November', 'Aralık': 'December'
    }
    for tr, en in turkish_to_english_months.items():
        date_str_raw = date_str_raw.replace(tr, en)
    
    date_obj = pd.to_datetime(date_str_raw, format='%B %d, %Y')
    date_standard = date_obj.strftime('%Y-%m-%d')
    
    return date_standard, price_int

async def scrape_calendar_prices(page):
    print("Starting to scrape and process calendar prices...")
    all_prices = []
    processed_raw_dates = set()
    DEFAULT_TIMEOUT = 20000

    async def process_visible_days():

        price_day_elements = await page.locator("span.flatpickr-day.DateInput__has-price:visible").all()
        for day_element in price_day_elements:
            raw_date = await day_element.get_attribute("aria-label")
            if raw_date and raw_date not in processed_raw_dates:
                raw_price = await day_element.locator("span.DateInput__day-price").inner_text()
                # CLEAN DATA AT THE SOURCE
                clean_date, clean_price = clean_and_parse_scraped_data(raw_date, raw_price)
                all_prices.append({"Date": clean_date, "Price": clean_price})
                processed_raw_dates.add(raw_date)

    print("\nStep 1: Scanning initially visible months...")
    try:
        await page.locator(".flatpickr-current-month").first.wait_for(timeout=DEFAULT_TIMEOUT)
        await page.wait_for_timeout(3000)
        await process_visible_days()
    except Exception as e:
        print(f"An error occurred while scraping initial months: {e}")

    for i in range(1): # Number of times to click the "next" button
        try:
            print(f"\nStep {i + 2}: Navigating to next months...")
            last_current_month_raw = (await page.locator(".flatpickr-current-month").all_inner_texts())[-1]
            next_month_button = page.locator(".flatpickr-calendar .DateInput__next-arrow:visible")
            await next_month_button.click(); await page.wait_for_timeout(500)
            await next_month_button.click()
            await page.locator(f".flatpickr-current-month:text-matches('{last_current_month_raw}')").last.wait_for(state='hidden', timeout=DEFAULT_TIMEOUT)
            await page.wait_for_timeout(500)
            await process_visible_days()
        except Exception as e:
            print(f"An error occurred in scraping step {i + 2}: {e}")
            continue
            
    return all_prices

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, slow_mo=50)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        try:
            print("Opening Pegasus website...")
            await page.goto("https://www.flypgs.com/")
            # --- ROBUST POP-UP HANDLING ---
            # Wait a moment for any pop-ups to appear
            await page.wait_for_timeout(5000)
            
            # Try to close any known pop-ups or overlays
            cookie_button = page.get_by_role("button", name="Kabul Et")
            if await cookie_button.is_visible():
                print("Cookie pop-up found. Accepting...")
                await cookie_button.click()
            
            # This is the overlay from your error log. We will click it if it exists.
            overlay = page.locator("div.c-modal-overlay")
            if await overlay.is_visible():
                print("Modal overlay found. Attempting to click it to close.")
                try:
                    await overlay.click(timeout=5000)
                except Exception:
                    print("Could not click overlay, pressing Escape key as a fallback.")
                    await page.keyboard.press("Escape")

            print("Entering flight details...")
            # Use force click to bypass potential remaining overlays
            await page.locator("#fromWhere").click(force=True, timeout=15000)
            await page.locator("#fromWhere").fill(DEPARTURE_CITY)
            await page.locator(f'.tstnm_fly_search_tab_1_departure_list_item[data-port-code="{DEPARTURE_PORT_CODE}"]').click()
            
            await page.locator("#toWhere").click(force=True, timeout=15000)
            await page.locator("#toWhere").fill(ARRIVAL_CITY)
            await page.locator(f'.tstnm_fly_search_tab_1_arrival_list_item[data-port-code="{ARRIVAL_PORT_CODE}"]').click()
            print("\n--- SCRAPING DEPARTURE PRICES ---")
            departure_data = await scrape_calendar_prices(page)
            if departure_data:
                pd.DataFrame(departure_data).to_csv(DEPARTURE_CSV_FILE, index=False)
                print(f"\n===> Clean departure prices saved to '{DEPARTURE_CSV_FILE}'.")
            else:
                return False

            await page.keyboard.press("Escape"); await page.wait_for_timeout(1000)
            
            print("\n--- SCRAPING RETURN PRICES ---")
            await page.locator('.tstnm_fly_search_tab_1_return_date_area').click()
            return_data = await scrape_calendar_prices(page)
            if return_data:
                pd.DataFrame(return_data).to_csv(RETURN_CSV_FILE, index=False)
                print(f"\n===> Clean return prices saved to '{RETURN_CSV_FILE}'.")
            else:
                return False
            return True
        except Exception as e:
            print(f"AN ERROR OCCURRED DURING THE MAIN SCRAPING PROCESS: {e}")
            await page.screenshot(path="error_screenshot.png")
            return False
        finally:
            print("Closing browser..."); await context.close(); await browser.close()

# ==============================================================================
# PART 2: ANALYSIS AND REPORTING
# ==============================================================================

def find_best_flight_combinations(departure_file, return_file, trip_durations):
    """
    Reads pre-cleaned CSV files and performs the analysis.
    """
    try:
        df_departure = pd.read_csv(departure_file, parse_dates=['Date'])
        df_return = pd.read_csv(return_file, parse_dates=['Date'])
    except FileNotFoundError as e:
        print(f"Error: CSV file for analysis not found -> {e}"); return None
    
    valid_combinations = []
    for _, departure_flight in df_departure.iterrows():
        for duration in trip_durations:
            target_return_date = departure_flight['Date'] + timedelta(days=duration)
            matching_returns = df_return[df_return['Date'] == target_return_date]
            for _, return_flight in matching_returns.iterrows():
                valid_combinations.append({
                    'Departure Date': departure_flight['Date'].strftime('%d-%m-%Y'),
                    'Return Date': target_return_date.strftime('%d-%m-%Y'),
                    'Trip Duration (Days)': duration,
                    'Total Price (TL)': departure_flight['Price'] + return_flight['Price']
                })
    if not valid_combinations:
        print("Analysis result: No valid flight combinations found for the given criteria.")
        return None
    return pd.DataFrame(valid_combinations).sort_values(by='Total Price (TL)', ascending=True)

def compare_and_report(new_results, archive_file):
    new_results['Departure Month'] = pd.to_datetime(new_results['Departure Date'], format='%d-%m-%Y').dt.strftime('%Y-%m')
    new_top_10_list = new_results.groupby('Departure Month').head(10)
    
    if not os.path.exists(archive_file):
        print("Archive file not found. This is the first run. Archiving current list.")
        new_top_10_list.drop(columns=['Departure Month']).to_csv(archive_file, index=False)
        report_df = new_top_10_list.rename(columns={'Total Price (TL)': 'Total Price (TL)_new'})
        report_df['Status'] = "Initial Record"
        return report_df

    old_top_10_list = pd.read_csv(archive_file)
    comparison_df = pd.merge(new_top_10_list, old_top_10_list, on=['Departure Date', 'Return Date'], how='outer', suffixes=('_new', '_old'))
    comparison_df.sort_values(by=['Departure Month', 'Total Price (TL)_new'], inplace=True, ignore_index=True)
    
    statuses = []
    for _, row in comparison_df.iterrows():
        old_price, new_price = row['Total Price (TL)_old'], row['Total Price (TL)_new']
        if pd.isna(old_price): statuses.append(f"NEW DEAL!")
        elif pd.isna(new_price): statuses.append(f"Removed from Top 10 (Old: {int(old_price)} TL)")
        elif new_price < old_price: statuses.append(f"PRICE DROP! (Old: {int(old_price)} TL)")
        elif new_price > old_price: statuses.append(f"Price Increase (Old: {int(old_price)} TL)")
        else: statuses.append("Same Price")
        
    comparison_df['Status'] = statuses
    new_top_10_list.drop(columns=['Departure Month']).to_csv(archive_file, index=False)
    print(f"Archive file '{archive_file}' has been updated.")
    return comparison_df

def send_email_report(report_df):
    deals = report_df[report_df['Status'].str.contains('NEW DEAL|PRICE DROP', regex=True, na=False)]
    if deals.empty:
        print("No new deals or price drops found. Email will not be sent.")
        return
        
    html = """
    <html><head><style>
      body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; }
      h2, h3 { color: #2E86C1; border-bottom: 2px solid #f2f2f2; padding-bottom: 5px;}
      table { border-collapse: collapse; width: 100%; margin: 20px 0; font-size: 14px; }
      th, td { border: 1px solid #dddddd; text-align: left; padding: 12px; }
      tr:nth-child(even) { background-color: #f2f2f2; }
      th { background-color: #4CAF50; color: white; }
      .status-new { color: #0000FF; font-weight: bold; }
      .status-dropped { color: #008000; font-weight: bold; }
    </style></head><body>
      <h2>&#9992;&#65039; Tirana Flight Price Alert Report</h2>
    """
    if not deals.empty:
        html += "<h3>Deals Summary (New or Price Drops)</h3>"
        deals_to_print = deals.rename(columns={'Total Price (TL)_new': 'New Price (TL)'})
        deals_html_table = deals_to_print[['Departure Date', 'Return Date', 'New Price (TL)', 'Status']].to_html(index=False, escape=False, na_rep="-")
        html += deals_html_table
    else:
        html += "<p><b>No new deals or price drops were found in this run.</b></p>"
    
    full_list_df = report_df[report_df['Total Price (TL)_new'].notna()].copy()
    if not full_list_df.empty:
        html += "<br><hr><br><h2>Top 10 Cheapest Flights Per Month (Full Current List)</h2>"
        for month_code, group in full_list_df.groupby('Departure Month'):
            departure_month_number = month_code.split('-')[1]
            html += f"<h3>Departure Month: {departure_month_number}</h3>"
            group_to_print = group[['Departure Date', 'Return Date', 'Trip Duration (Days)_new', 'Total Price (TL)_new', 'Status']].rename(columns={
                'Trip Duration (Days)_new': 'Duration (Days)', 'Total Price (TL)_new': 'Price (TL)'
            })
            html += group_to_print.to_html(index=False, escape=False, na_rep="-") + "<br>"
            
    html += """<p style="font-size:small; color:grey;">This email was sent automatically by the Python Flight Tracker script.</p></body></html>"""

    message = MIMEMultipart("alternative")
    message["Subject"] = "Tirana Flight Tracker: New Deals Found!"
    message["From"] = SENDER_EMAIL
    message["To"] = ", ".join(RECIPIENT_EMAILS)
    message.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, EMAIL_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAILS, message.as_string())
            print(f"Detailed report email sent successfully! Recipients: {', '.join(RECIPIENT_EMAILS)}")
    except Exception as e:
        print(f"ERROR SENDING EMAIL: {e}")
        print("PLEASE NOTE: Check your email settings (especially the password). You must use an 'App Password' for Gmail, not your regular password.")

# ==============================================================================
# PART 3: MAIN EXECUTION LOGIC
# ==============================================================================

def main():
    print("="*50 + "\nFLIGHT AUTOMATION SCRIPT STARTED\n" + "="*50)
    
    print("\n[PHASE 1/3] Scraping current flight data from the website...")
    if not asyncio.run(run_scraper()):
        print("\n[ERROR] Data scraping failed. Halting script.")
        return

    print("\n[PHASE 2/3] Calculating best flight combinations from scraped data...")
    all_results = find_best_flight_combinations(DEPARTURE_CSV_FILE, RETURN_CSV_FILE, TRIP_DURATIONS)
    if all_results is None:
        print("\n[ERROR] Could not calculate flight combinations. Halting script.")
        return

    print("\n[PHASE 3/3] Comparing new results with archive and generating report...")
    report_df = compare_and_report(all_results, ARCHIVE_CSV_FILE)
    
    print("\nComparison report generated. Printing to screen...")
    print("="*80)
    report_df_print = report_df.copy()
    report_df_print['Total Price (TL)'] = report_df_print['Total Price (TL)_new'].fillna(report_df_print['Total Price (TL)_old'])
    for month_code, group in report_df_print.groupby('Departure Month'):
        if pd.isna(month_code): continue
        departure_month_number = str(month_code).split('-')[1]
        print(f"--- Departure Month: {departure_month_number} ---\n")
        group_to_print = group[['Departure Date', 'Return Date', 'Total Price (TL)', 'Status']]
        print(group_to_print.to_string(index=False), "\n" + "-"*50 + "\n")
    
    print("Initiating email process...")
    send_email_report(report_df)
    
    print("\n="*5 + "\nAUTOMATION COMPLETE\n" + "="*5)

if __name__ == "__main__":
    main()
