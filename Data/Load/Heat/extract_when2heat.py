import pandas as pd
from datetime import datetime
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

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

# Convert utc_timestamp to datetime 
df['utc_timestamp'] = pd.to_datetime(df['utc_timestamp'])

# Select the required columns
required_columns = [
    'utc_timestamp',
    'FR_heat_demand_space_SFH',
    'FR_heat_demand_water',
    'FR_COP_ASHP_water',
    'FR_COP_GSHP_floor'
]

# Process multiple dates
target_dates = [
    datetime(2015, 4, 15),   # April 15, 2015
    datetime(2015, 7, 15),   # July 15, 2015
    datetime(2015, 10, 15),  # October 15, 2015
    datetime(2015, 1, 15)    # January 15, 2015
]

for target_date in target_dates:
    print("\n" + "="*80)
    print(f"Processing date: {target_date.strftime('%d.%m.%Y')}")
    print("="*80)
    
    # Filter for target date
    df_filtered = df[df['utc_timestamp'].dt.date == target_date.date()]
    
    # Extract the table with required columns
    result_table = df_filtered[required_columns].copy()
    
    # Reset index for cleaner display
    result_table = result_table.reset_index(drop=True)
    
    print(f"\nExtracted data for {target_date.strftime('%d.%m.%Y')} (Hourly Information)")
    print(f"Total records found: {len(result_table)}")
    print("\nData Table:")
    print(result_table.to_string())
    
    # Save to CSV
    output_filename = f'extracted_when2heat_FR_{target_date.strftime("%d_%m_%Y")}.csv'
    result_table.to_csv(output_filename, index=False)
    print(f"\nData saved to: {output_filename}")
    
    # Generate graph
    plt.figure(figsize=(12, 6))
    
    # Plot both heat demand columns
    plt.plot(result_table['utc_timestamp'], result_table['FR_heat_demand_space_SFH'], 
             marker='o', linewidth=2, markersize=4, label='Space Heating Demand (SFH)', color='#FF6B6B')
    plt.plot(result_table['utc_timestamp'], result_table['FR_heat_demand_water'], 
             marker='s', linewidth=2, markersize=4, label='Water Heating Demand', color='#4ECDC4')
    
    # Format and label axes
    plt.xlabel('Time of Day', fontsize=12, fontweight='bold')
    plt.ylabel('Thermal Demand (W)', fontsize=12, fontweight='bold')
    plt.title(f'Thermal Demand for France - {target_date.strftime("%B %d, %Y")}', fontsize=14, fontweight='bold')
    
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
    figure_filename = f'heat_demand_graph_FR_{target_date.strftime("%d_%m_%Y")}.png'
    plt.savefig(figure_filename, dpi=300, bbox_inches='tight')
    print(f"Graph saved to: {figure_filename}")
    
    # Close figure to free memory
    plt.close()
