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

| Metric | Description |
|--------|-------------|
| Timestamp | When the cleaning session ended |
| Clean Time | Duration in minutes |
| Clean Area | Area cleaned in m² |
| Battery Start/End | Battery level before and after cleaning |
| Fan Power | Suction power setting |
| Mop Mode | Mopping mode setting |
| Error Code | Any error that occurred |

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

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable **Google Sheets API**:
   - Go to "APIs & Services" > "Library"
   - Search for "Google Sheets API"
   - Click "Enable"
4. Create Service Account:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "Service Account"
   - Give it a name and create
5. Download JSON Key:
   - Click on the service account
   - Go to "Keys" tab
   - "Add Key" > "Create new key" > JSON
   - Save as `config/credentials.json`

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
- Verify `credentials.json` is in the `config/` folder
- Ensure Google Sheets API is enabled in your project
- Check the service account has no restrictions

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
