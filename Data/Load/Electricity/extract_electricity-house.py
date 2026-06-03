import pandas as pd
from datetime import datetime
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

df = pd.read_csv('gas_house-summary.csv', on_bad_lines='skip')
df.rename(columns={df.columns[0]: 'Timestamp'}, inplace=True)
df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True)

required_columns = ['Timestamp', 'Mean', 'Median']
target_dates = [
    datetime(2022, 10, 25),
    datetime(2023, 1, 15),
    datetime(2023, 4, 15),
    datetime(2023, 7, 15)
]

for target_date in target_dates:
    df_filtered = df[df['Timestamp'].dt.date == target_date.date()]
    df_hourly = df_filtered[df_filtered['Timestamp'].dt.minute == 0].copy()

    output_filename = f'extracted_gas_house_{target_date.strftime("%d_%m_%Y")}.csv'
    df_hourly[required_columns].to_csv(output_filename, index=False)

    plt.figure(figsize=(12, 6))
    plt.plot(df_hourly['Timestamp'], df_hourly['Mean'],
             marker='o', linewidth=2, markersize=6,
             label='Mean Electricity Consumption', color='#FF6B6B')
    plt.plot(df_hourly['Timestamp'], df_hourly['Median'],
             marker='s', linewidth=2, markersize=6,
             label='Median Electricity Consumption', color='#4ECDC4')

    plt.xlabel('Time of Day (Hours)', fontsize=12, fontweight='bold')
    plt.ylabel('Electricity Consumption (W)', fontsize=12, fontweight='bold')
    plt.title(f'Hourly Electricity Consumption - {target_date.strftime("%d.%m.%Y")}', fontsize=14, fontweight='bold')

    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 2)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    plt.xticks(rotation=45, ha='right')

    plt.grid(True, alpha=0.3, linestyle='--')
    plt.legend(loc='best', fontsize=11, framealpha=0.9)
    plt.tight_layout()

    figure_filename = f'electricity_consumption_graph_{target_date.strftime("%d_%m_%Y")}.png'
    plt.savefig(figure_filename, dpi=300, bbox_inches='tight')
    plt.close()
