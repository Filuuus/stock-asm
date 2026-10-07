# ZeekGPS to Notion - Fleet Automation

This project contains a set of Python scripts designed to automate the extraction of trip histories from the ZeekGPS API and sync them directly with a Notion workspace. 

Ideal for fleet management, automated mileage calculation, and maintaining clean digital logs.

## Features

* **Daily Report (`reporte_diario.py`):** 
  * Queries the trips made by each vehicle on the previous day.
  * Extracts start/end times, distances, durations, and locations.
  * Generates a complete route link in Google Maps.
  * Overwrites the total odometer in each vehicle's master card.
  * Creates a detailed record in the Daily Log database in Notion.
* **Monthly Close (`cierre_mensual.py`):** 
  * Consolidates all daily trips for a vehicle during the month.
  * Generates a unified monthly report per vehicle.
  * Automatically archives (hides) the daily records of the processed month to keep the database clean without losing the history.

## Prerequisites

* **Python 3.7+**
* An integration (Bot) created in [Notion Developers](https://www.notion.so/my-integrations) with read and write permissions.
* The Notion bot must have access (invited) to the vehicle and log databases.
* API access credentials for ZeekGPS.

## Installation

1. Clone this repository:

  ```bash 
   git clone [https://github.com/Filuuus/stock-asm.git](https://github.com/Filuuus/stock-asm.git)
   cd stock-asm
  ```


2. Install the necessary dependencies:

  ```bash
  pip install requests
  ```

3. Create a file named `.env` in the root of the project based on the example file:

  ```bash
  cp .env.example .env
  ```

## Configuration

Open the `.env` file and enter your actual credentials. **(Never upload this file to GitHub)**:

```env
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DATABASE_BITACORA_ID=your_database_id_here
ZEEK_TOKEN=your_zeek_token
ZEEK_CLIENTE=zeek_client_name
ZEEK_LICENCIA=your_zeek_license
```


### Fleet Configuration

In the `reporte_diario.py` file, make sure to update the `flotilla` dictionary with your vehicles' actual ZeekGPS IDs and the exact Page IDs of the master cards in Notion:

```python
flotilla = {
    "ZEEK_VEHICLE_ID": {"nombre": "Vehicle Name", "notion_page_id": "NOTION_PAGE_ID"},
}

```

## Usage

### Daily Execution

It is recommended to run this script on a schedule (cron job, GitHub Actions, AWS EventBridge, etc.) every morning to record the previous day's activity.

```bash
python reporte_diario.py

```

### Monthly Execution

It is recommended to run this script on the first day of each month to consolidate and clean up the records of the month that just ended.

```bash
python cierre_mensual.py

```

## 🔒 Security

Sensitive credentials are handled exclusively through environment variables (`os.getenv`). The `.env` file is excluded from version control via `.gitignore` to prevent data leaks.

```

```