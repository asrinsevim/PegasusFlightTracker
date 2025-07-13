# Flight Price Tracker & Notifier

![Flight Price Tracker Automation](https://github.com/asrinsevim/PegasusFlightTracker/actions/workflows/flight-tracker.yml/badge.svg)

This project automates the process of tracking round-trip flight prices for a specified route on Pegasus Airlines. It scrapes the latest prices, compares them against a historical archive of the best deals, identifies new deals and price drops, and sends a detailed HTML email report with the findings.

The entire process is designed to run automatically every 24 hours using GitHub Actions.

## Key Features

-   **Automated Scraping:** Uses Playwright to automatically navigate the website and scrape flight prices from the calendar view.
-   **Price Combination:** Calculates total prices for round-trip combinations based on predefined trip durations (e.g., 6, 7, or 8 days).
-   **Historical Comparison:** Compares the latest top 10 cheapest flights per month against the previously saved list to track changes.
-   **Deal Detection:** Identifies and flags several statuses for flight deals:
    -   `PRICE DROP!`
    -   `NEW DEAL!`
    -   `Price Increase`
    -   `Removed from Top 10`
-   **Email Notifications:** Sends a well-formatted HTML email report that highlights new deals and price drops, and also includes the full list of the current top 10 deals for each month.
-   **Fully Automated:** The entire workflow is scheduled to run every 24 hours via GitHub Actions, requiring no manual intervention.
-   **Secure:** Manages the email password securely using GitHub Actions Secrets instead of hardcoding it into the script.

## How It Works

The automation follows a simple, robust pipeline:

1.  **Scheduled Trigger:** The GitHub Actions workflow is triggered automatically on a schedule (e.g., every 24 hours).
2.  **Scrape Data:** The Python script launches a Playwright instance, navigates to the airline's website, and scrapes departure and return prices for all available months. The data is saved into `departure_prices.csv` and `return_prices.csv`.
3.  **Analyze & Compare:** The script then processes these CSV files, calculates the total price for all valid round-trip combinations, and finds the top 10 cheapest deals for each month. This new list is compared against the data in `previous_results.csv`.
4.  **Generate Report:** Based on the comparison, a comprehensive report is generated, marking the status of each flight deal.
5.  **Notify:** If any new deals or price drops are found, the script sends an HTML email to the specified recipients.
6.  **Archive & Commit:** Finally, the script overwrites the `previous_results.csv` file with the latest top 10 deals. The GitHub Actions workflow then automatically commits this updated archive file back to the repository, ensuring the next run compares against the most recent data.


## Usage

### Automated Execution
The primary way to use this project is to let the automation run. The workflow is scheduled to trigger automatically at 19:00 UTC (10:00 AM and 10:00 PM Turkey Time) as defined in `flight-tracker.yml`.

### Manual Execution
You can also trigger a run manually at any time:
1.  Go to the **"Actions"** tab in your GitHub repository.
2.  In the left sidebar, click on **"Flight Price Tracker Automation"**.
3.  Click on the **"Run workflow"** dropdown on the right, and then click the green **"Run workflow"** button.

## Technology Stack

-   **Language:** Python
-   **Automation/Scraping:** Playwright
-   **Data Manipulation:** Pandas
-   **CI/CD & Scheduling:** GitHub Actions
