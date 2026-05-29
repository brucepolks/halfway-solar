VERSOFY SOLAR ANALYTICS
========================

FIRST TIME SETUP:
1. Double-click START.command to launch
   (macOS may ask for permission — right-click → Open)
2. The app installs its dependencies automatically on first run
3. Your browser opens automatically at http://localhost:5050

USING THE APP:
1. Add your clients (name + Dash IOT site ID)
2. Click "New Analysis", select a client, upload their electricity bill PDF
3. Review the extracted data, then click Generate
4. The app logs into Dash IOT, pulls the data, and builds the report
5. Share the report link directly with your client or download the Excel

FINDING SITE IDs:
- Log into dash-iot.com
- The site selector dropdown option values are the Site IDs
- e.g. Kiara Bottom = 50, Kiara Top = 49

STOPPING THE APP:
- Press Ctrl+C in the terminal window, or close the terminal

CREDENTIALS:
- Stored in Settings (localhost:5050/settings)
- Currently set to your bruce/Mufasa123 credentials

SUPPORT:
- All reports saved in the /reports/ folder
- Database at /database/solar.db
