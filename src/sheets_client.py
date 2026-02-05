"""
Google Sheets Client Module
Handles data storage and retrieval from Google Sheets
"""

import os
from datetime import datetime
from typing import List, Any, Optional
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# Scopes required for Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


class GoogleSheetsClient:
    """
    Client for interacting with Google Sheets API.
    Handles creating spreadsheets, sheets, and writing data.
    """
    
    def __init__(self, credentials_path: str, spreadsheet_id: Optional[str] = None):
        """
        Initialize the Google Sheets client.
        
        Args:
            credentials_path: Path to service account JSON file
            spreadsheet_id: Optional existing spreadsheet ID
        """
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Sheets API using service account."""
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_path}\n"
                "Please download your service account credentials from Google Cloud Console."
            )
        
        credentials = Credentials.from_service_account_file(
            self.credentials_path, 
            scopes=SCOPES
        )
        self.service = build('sheets', 'v4', credentials=credentials)
        print("[INFO] Successfully authenticated with Google Sheets API")
    
    def create_spreadsheet(self, title: str) -> str:
        """
        Create a new spreadsheet.
        
        Args:
            title: Name of the spreadsheet
            
        Returns:
            Spreadsheet ID
        """
        spreadsheet = {
            'properties': {'title': title}
        }
        
        result = self.service.spreadsheets().create(
            body=spreadsheet,
            fields='spreadsheetId'
        ).execute()
        
        self.spreadsheet_id = result.get('spreadsheetId')
        print(f"[INFO] Created spreadsheet: {title}")
        print(f"[INFO] Spreadsheet ID: {self.spreadsheet_id}")
        print(f"[INFO] URL: https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}")
        
        return self.spreadsheet_id
    
    def create_sheet(self, sheet_name: str):
        """
        Create a new sheet (tab) in the spreadsheet.
        
        Args:
            sheet_name: Name of the sheet to create
        """
        try:
            request = {
                'requests': [{
                    'addSheet': {
                        'properties': {'title': sheet_name}
                    }
                }]
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=request
            ).execute()
            
            print(f"[INFO] Created sheet: {sheet_name}")
            
        except HttpError as e:
            if 'already exists' in str(e):
                print(f"[INFO] Sheet '{sheet_name}' already exists")
            else:
                raise
    
    def write_headers(self, sheet_name: str, headers: List[str]):
        """
        Write header row to a sheet.
        
        Args:
            sheet_name: Name of the sheet
            headers: List of column headers
        """
        range_name = f"{sheet_name}!A1"
        
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            body={'values': [headers]}
        ).execute()
        
        print(f"[INFO] Wrote headers to {sheet_name}")
    
    def append_row(self, sheet_name: str, row_data: List[Any]):
        """
        Append a single row of data to a sheet.
        
        Args:
            sheet_name: Name of the sheet
            row_data: List of values for the row
        """
        range_name = f"{sheet_name}!A:K"
        
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': [row_data]}
        ).execute()
        
        print(f"[INFO] Appended row to {sheet_name}")
    
    def append_rows(self, sheet_name: str, rows_data: List[List[Any]]):
        """
        Append multiple rows of data to a sheet.
        
        Args:
            sheet_name: Name of the sheet
            rows_data: List of rows, each row is a list of values
        """
        if not rows_data:
            return
            
        range_name = f"{sheet_name}!A:K"
        
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': rows_data}
        ).execute()
        
        print(f"[INFO] Appended {len(rows_data)} rows to {sheet_name}")
    
    def get_all_values(self, sheet_name: str) -> List[List[Any]]:
        """
        Get all values from a sheet.
        
        Args:
            sheet_name: Name of the sheet
            
        Returns:
            List of rows (each row is a list of values)
        """
        range_name = f"{sheet_name}!A:Z"
        
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name
        ).execute()
        
        return result.get('values', [])
    
    def get_last_row_number(self, sheet_name: str) -> int:
        """
        Get the number of the last row with data.
        
        Args:
            sheet_name: Name of the sheet
            
        Returns:
            Row number (1-indexed)
        """
        values = self.get_all_values(sheet_name)
        return len(values)
    
    def format_header_row(self, sheet_name: str, sheet_id: int = 0):
        """
        Apply formatting to the header row (bold, background color).
        
        Args:
            sheet_name: Name of the sheet
            sheet_id: Sheet ID (get from sheet properties)
        """
        requests = [
            {
                'repeatCell': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 0,
                        'endRowIndex': 1
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': {
                                'red': 0.2,
                                'green': 0.4,
                                'blue': 0.8
                            },
                            'textFormat': {
                                'bold': True,
                                'foregroundColor': {
                                    'red': 1.0,
                                    'green': 1.0,
                                    'blue': 1.0
                                }
                            }
                        }
                    },
                    'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                }
            },
            {
                'updateSheetProperties': {
                    'properties': {
                        'sheetId': sheet_id,
                        'gridProperties': {'frozenRowCount': 1}
                    },
                    'fields': 'gridProperties.frozenRowCount'
                }
            }
        ]
        
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={'requests': requests}
        ).execute()
        
        print(f"[INFO] Formatted header row in {sheet_name}")


def setup_roborock_spreadsheet(
    credentials_path: str,
    spreadsheet_name: str = "Roborock_Q8_Data"
) -> GoogleSheetsClient:
    """
    Set up a new spreadsheet with sheets for Roborock data.
    
    Args:
        credentials_path: Path to service account JSON file
        spreadsheet_name: Name for the spreadsheet
        
    Returns:
        Configured GoogleSheetsClient instance
    """
    from src.roborock_collector import (
        CLEANING_HISTORY_HEADERS, 
        DEVICE_STATUS_HEADERS,
        CLEAN_SUMMARY_HEADERS,
        CONSUMABLES_HEADERS
    )
    
    client = GoogleSheetsClient(credentials_path)
    client.create_spreadsheet(spreadsheet_name)
    
    # Create Cleaning History sheet
    client.create_sheet("Cleaning_History")
    client.write_headers("Cleaning_History", CLEANING_HISTORY_HEADERS)
    
    # Create Device Status sheet
    client.create_sheet("Device_Status")
    client.write_headers("Device_Status", DEVICE_STATUS_HEADERS)
    
    # Create Clean Summary sheet (lifetime stats)
    client.create_sheet("Clean_Summary")
    client.write_headers("Clean_Summary", CLEAN_SUMMARY_HEADERS)
    
    # Create Consumables sheet
    client.create_sheet("Consumables")
    client.write_headers("Consumables", CONSUMABLES_HEADERS)
    
    # Create Daily Summary sheet
    client.create_sheet("Daily_Summary")
    client.write_headers("Daily_Summary", [
        "Date",
        "Total Cleanings",
        "Total Clean Time (min)",
        "Total Area (m²)",
        "Avg Clean Time (min)",
        "Avg Area (m²)"
    ])
    
    # Remove default Sheet1
    try:
        sheets = client.service.spreadsheets().get(
            spreadsheetId=client.spreadsheet_id
        ).execute().get('sheets', [])
        
        for sheet in sheets:
            if sheet['properties']['title'] == 'Sheet1':
                client.service.spreadsheets().batchUpdate(
                    spreadsheetId=client.spreadsheet_id,
                    body={'requests': [{'deleteSheet': {'sheetId': sheet['properties']['sheetId']}}]}
                ).execute()
                break
    except:
        pass
    
    print("\n[SUCCESS] Spreadsheet setup complete!")
    print(f"[INFO] Share this spreadsheet with your Google account to view it.")
    
    return client
