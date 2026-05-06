import pandas as pd
from datetime import datetime
import os

# Get the file size
file_size = os.path.getsize('when2heat.csv') / (1024*1024)
print(f"File size: {file_size:.2f} MB")

# Load the CSV file with semicolon delimiter
df = pd.read_csv('when2heat.csv', sep=';', on_bad_lines='skip')

# Display the first few rows to understand the data structure
print("CSV file structure:")
print(df.head())
print("\nColumn names:")
print(df.columns.tolist())
print(f"\nTotal rows: {len(df)}")

# Convert utc_timestamp to datetime if it's not already
df['utc_timestamp'] = pd.to_datetime(df['utc_timestamp'])

# Filter for June 1, 2015
target_date = datetime(2015, 6, 1)
df_filtered = df[df['utc_timestamp'].dt.date == target_date.date()]

# Select the required columns
required_columns = [
    'utc_timestamp',
    'FR_heat_demand_space_SFH',
    'FR_heat_demand_water',
    'FR_COP_ASHP_water',
    'FR_COP_GSHP_floor'
]

# Extract the table with required columns
result_table = df_filtered[required_columns].copy()

# Reset index for cleaner display
result_table = result_table.reset_index(drop=True)

print("\n" + "="*80)
print(f"Extracted data for {target_date.strftime('%d.%m.%Y')} (Hourly Information)")
print("="*80)
print(f"\nTotal records found: {len(result_table)}")
print("\nData Table:")
print(result_table.to_string())

# Optional: Save to CSV
output_filename = f'extracted_when2heat_FR_{target_date.strftime("%d_%m_%Y")}.csv'
result_table.to_csv(output_filename, index=False)
print(f"\nData saved to: {output_filename}")
