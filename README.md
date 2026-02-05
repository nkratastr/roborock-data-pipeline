# Roborock Q8 Data Engineering Pipeline

A data pipeline that collects cleaning metrics from your Roborock Q8 vacuum and stores them in Google Sheets for analysis.

## Features

- **Automatic Data Collection**: Monitors your Roborock Q8 and logs cleaning sessions
- **Google Sheets Integration**: Stores data in a cloud spreadsheet for easy access and visualization
- **Event-Driven**: Captures data when cleaning completes
- **Multiple Modes**: Monitor continuously, quick status check, or manual logging

## Project Structure

```
Roborock_Q8/
├── config/
│   ├── settings.py           # Configuration settings
│   └── credentials.json      # Google Sheets API credentials (you create this)
├── src/
│   ├── roborock_collector.py # Roborock API data extraction
│   └── sheets_client.py      # Google Sheets API integration  
├── pipeline.py               # Main data pipeline script
├── roborock_connect.py       # Simple connection test script
├── requirements.txt          # Python dependencies
└── README.md
```

## Data Collected

### Cleaning History
Each cleaning session captures:
- Timestamp, clean time (minutes), clean area (m²)
- Battery start/end levels
- Fan power, mop mode, water level
- Error codes (if any)

### Device Status
Real-time device state:
- Current state (charging, cleaning, idle)
- Battery level, fan power
- Clean area and time for current/last session
- Water box status and mode

### Clean Summary (Lifetime Stats)
- Total number of cleanings
- Total area cleaned (m²)
- Total cleaning time (minutes)
- Records updated timestamp

### Consumables
Track maintenance items:
- Main brush work time (hours)
- Side brush work time (hours)
- Filter work time (hours)
- Sensor dirty time (hours)
- Mop pad work time (hours)

## Setup Instructions

### 1. Install Python

Download and install Python 3.10+ from https://www.python.org/downloads/

**Important**: Check "Add Python to PATH" during installation.

### 2. Install Dependencies

```bash
cd Roborock_Q8
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your Roborock email
ROBOROCK_EMAIL=your-email@example.com
```

### 4. Set Up Google Sheets API

#### Step-by-Step Guide

**A. Create Google Cloud Project**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown (top left)
3. Click "New Project"
4. Name it (e.g., `roborock-pipeline`)
5. Click "Create" and wait for it to complete

**B. Enable Google Sheets API**
1. In the search bar, type "Google Sheets API"
2. Click on "Google Sheets API" in results
3. Click the blue "ENABLE" button

**C. Create Service Account**
1. Go to "IAM & Admin" → "Service Accounts" (left menu)
2. Click "+ CREATE SERVICE ACCOUNT"
3. Enter service account details:
   - Name: `roborock-data` (or any name you prefer)
   - ID will auto-fill
4. Click "CREATE AND CONTINUE"
5. Skip role assignment (click "CONTINUE")
6. Click "DONE"

**D. Download Credentials JSON**
1. Click on the service account you just created
2. Go to "KEYS" tab
3. Click "ADD KEY" → "Create new key"
4. Select "JSON" format
5. Click "CREATE" - file downloads automatically
6. Rename the downloaded file to `credentials.json`
7. Move it to the `config/` folder in your project

**E. Set Up Spreadsheet (Choose ONE option)**

**Option 1: Create New Spreadsheet Automatically**
- The pipeline will create a new spreadsheet on first run
- Requires enabling Google Drive API:
  1. Search "Google Drive API" in Cloud Console
  2. Click "ENABLE"

**Option 2: Use Existing Spreadsheet (Recommended)**
1. Create a new Google Spreadsheet at https://sheets.google.com/
2. Name it "Roborock_Q8_Data" (or any name)
3. Click the **Share** button (top right)
4. Add the service account email (found in `credentials.json` as `client_email`)
   - Format: `your-name@your-project.iam.gserviceaccount.com`
5. Give it **Editor** permissions
6. Copy the spreadsheet ID from the URL
   - URL format: `https://docs.google.com/spreadsheets/d/[SPREADSHEET_ID]/edit`
7. Create a file `config/spreadsheet_id.txt` with just the ID

#### Spreadsheet Structure

The pipeline creates these sheets:

| Sheet Name | Content |
|------------|---------|
| Cleaning_History | Log of each cleaning session |
| Device_Status | Current/latest device state |
| Clean_Summary | Lifetime statistics |
| Consumables | Brush/filter work hours |
| Daily_Summary | Aggregated daily metrics |

### 5. Run the Pipeline

#### Quick Status Check
```bash
python pipeline.py --mode status
```

#### Continuous Monitoring
```bash
python pipeline.py --mode monitor
```

#### Manual Log Current Data
```bash
python pipeline.py --mode log
```

## Usage Flow

1. **First Run**: The script will:
   - Send a verification code to your Roborock account email
   - Create a new Google Spreadsheet
   - Start monitoring your device

2. **Subsequent Runs**: 
   - Uses saved spreadsheet ID
   - Just needs Roborock verification code

3. **Data Access**:
   - Open the Google Spreadsheet URL shown in console
   - Share with your Google account if using service account
   - Create charts/dashboards in Google Sheets

## Dashboard Ideas

Once data is collected, create these visualizations in Google Sheets:

1. **Cleaning Frequency Chart**: Line chart of cleanings per day/week
2. **Area Coverage**: Bar chart of m² cleaned per session
3. **Battery Usage**: Track battery drain per cleaning
4. **Cleaning Duration Trend**: Monitor if cleanings are taking longer over time

## Troubleshooting

### Python not found
- Reinstall Python and ensure "Add to PATH" is checked
- Restart your terminal after installation

### Roborock authentication fails
- Verify your email is correct in `.env` file
- Check your email (including spam) for the verification code
- Make sure you're using the Roborock app email, not Xiaomi Home

### Google Sheets errors
- **"The caller does not have permission"**: Enable Google Drive API OR share an existing spreadsheet with the service account email
- **"Unable to parse range"**: The sheet tabs don't exist - run the pipeline once to create them
- Verify `credentials.json` is in the `config/` folder
- Ensure Google Sheets API is enabled in your project
- Check the service account email in `credentials.json` matches what you shared the spreadsheet with

### Data not appearing
- Verify you shared the spreadsheet with the service account email (found in `credentials.json`)
- Give the service account **Editor** permissions (not just Viewer)
- Check the spreadsheet has the correct sheets created

## Security Notes

⚠️ **Important**: The following files contain sensitive credentials and are automatically excluded from Git:

- `.env` - Your Roborock email
- `config/credentials.json` - Google API credentials
- `config/spreadsheet_id.txt` - Your spreadsheet ID

Never commit these files to public repositories. Use `.env.example` as a template.

## Configuration

Edit `.env` file to set your credentials:

```bash
ROBOROCK_EMAIL=your-email@example.com
```

Edit `config/settings.py` for other settings:

```python
POLLING_INTERVAL_SECONDS = 60  # How often to check device status
```

## License

MIT License
