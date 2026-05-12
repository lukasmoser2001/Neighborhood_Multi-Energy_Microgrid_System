import pandas as pd
from datetime import datetime
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Get the file size
file_size = os.path.getsize('gas_house-summary.csv') / (1024*1024)
print(f"File size: {file_size:.2f} MB")

# Load the CSV file (comma delimiter)
df = pd.read_csv('gas_house-summary.csv', on_bad_lines='skip')

# Display the first few rows to understand the data structure
print("CSV file structure:")
print(df.head(10))
print("\nColumn names:")
print(df.columns.tolist())
print(f"\nTotal rows: {len(df)}")

# The first column is the timestamp (unnamed)
# Rename it to 'Timestamp' for clarity
df.rename(columns={df.columns[0]: 'Timestamp'}, inplace=True)

# Convert Timestamp to datetime, handling timezone info
df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True)

# Select the required columns (Mean and Median)
required_columns = ['Timestamp', 'Mean', 'Median']

# Process multiple dates
target_dates = [
    datetime(2022, 10, 25),  # October 25, 2022
    datetime(2023, 1, 15),   # January 15, 2023
    datetime(2023, 4, 15),   # April 15, 2023
    datetime(2023, 7, 15)    # July 15, 2023
]

for target_date in target_dates:
    print("\n" + "="*80)
    print(f"Processing date: {target_date.strftime('%d.%m.%Y')}")
    print("="*80)
    
    # Filter for target date
    df_filtered = df[df['Timestamp'].dt.date == target_date.date()]
    
    # Filter for hourly data (keep records where minute is :00)
    df_hourly = df_filtered[df_filtered['Timestamp'].dt.minute == 0].copy()
    
    # Extract the table with required columns
    result_table = df_hourly[required_columns].copy()
    
    # Reset index for cleaner display
    result_table = result_table.reset_index(drop=True)
    
    # Add hour column for better readability
    result_table['Hour'] = result_table['Timestamp'].dt.strftime('%H:%M')
    
    print(f"\nExtracted data for {target_date.strftime('%d.%m.%Y')} (Hourly Information)")
    print(f"Total records found: {len(result_table)}")
    print("\nData Table:")
    print(result_table[['Hour', 'Mean', 'Median']].to_string(index=False))
    
    # Save to CSV
    output_filename = f'extracted_gas_house_{target_date.strftime("%d_%m_%Y")}.csv'
    result_table[['Timestamp', 'Mean', 'Median']].to_csv(output_filename, index=False)
    print(f"\nData saved to: {output_filename}")
    
    # Generate graph
    plt.figure(figsize=(12, 6))
    
    # Plot both mean and median electricity columns
    plt.plot(result_table['Timestamp'], result_table['Mean'], 
             marker='o', linewidth=2, markersize=6, label='Mean Electricity Consumption', color='#FF6B6B')
    plt.plot(result_table['Timestamp'], result_table['Median'], 
             marker='s', linewidth=2, markersize=6, label='Median Electricity Consumption', color='#4ECDC4')
    
    # Format and label axes
    plt.xlabel('Time of Day (Hours)', fontsize=12, fontweight='bold')
    plt.ylabel('Electricity Consumption (W)', fontsize=12, fontweight='bold')
    plt.title(f'Hourly Electricity Consumption - {target_date.strftime("%d.%m.%Y")}', fontsize=14, fontweight='bold')
    
    # Format x-axis to show hours
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 2)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    plt.xticks(rotation=45, ha='right')
    
    # Add grid for better readability
    plt.grid(True, alpha=0.3, linestyle='--')
    
    # Add legend
    plt.legend(loc='best', fontsize=11, framealpha=0.9)
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Save figure
    figure_filename = f'electricity_consumption_graph_{target_date.strftime("%d_%m_%Y")}.png'
    plt.savefig(figure_filename, dpi=300, bbox_inches='tight')
    print(f"Graph saved to: {figure_filename}")
    
    # Close figure to free memory
    plt.close()

print("\n" + "="*80)
print("Data extraction and visualization complete!")
print("="*80)
