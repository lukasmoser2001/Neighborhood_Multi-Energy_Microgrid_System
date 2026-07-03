import pandas as pd
from datetime import datetime
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

df = pd.read_csv('when2heat.csv', sep=';', on_bad_lines='skip')
df['utc_timestamp'] = pd.to_datetime(df['utc_timestamp'])

required_columns = [
    'utc_timestamp',
    'FR_heat_demand_space_SFH',
    'FR_heat_demand_water',
    'FR_COP_ASHP_water',
    'FR_COP_GSHP_floor'
]

target_dates = [
    datetime(2015, 4, 15),
    datetime(2015, 7, 15),
    datetime(2015, 10, 15),
    datetime(2015, 1, 15)
]

for target_date in target_dates:
    df_filtered = df[df['utc_timestamp'].dt.date == target_date.date()]
    result_table = df_filtered[required_columns].copy()

    # Divide thermal demand values by 10 to correct the reported input values.
    result_table['FR_heat_demand_space_SFH'] = pd.to_numeric(
        result_table['FR_heat_demand_space_SFH'], errors='coerce') / 10
    result_table['FR_heat_demand_water'] = pd.to_numeric(
        result_table['FR_heat_demand_water'], errors='coerce') / 10

    output_filename = f'extracted_when2heat_FR_{target_date.strftime("%d_%m_%Y")}.csv'
    result_table.to_csv(output_filename, index=False)

    plt.figure(figsize=(12, 6))
    plt.plot(result_table['utc_timestamp'], result_table['FR_heat_demand_space_SFH'],
             marker='o', linewidth=2, markersize=4,
             label='Space Heating Demand', color='#FF6B6B')
    plt.plot(result_table['utc_timestamp'], result_table['FR_heat_demand_water'],
             marker='s', linewidth=2, markersize=4,
             label='Water Heating Demand', color='#4ECDC4')

    plt.xlabel('Time of Day', fontsize=12, fontweight='bold')
    plt.ylabel('Thermal Demand (W)', fontsize=12, fontweight='bold')
    plt.title(f'Thermal Demand for France - {target_date.strftime("%B %d, %Y")}', fontsize=14, fontweight='bold')

    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 2)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    plt.xticks(rotation=45, ha='right')

    plt.grid(True, alpha=0.3, linestyle='--')
    plt.ylim(0, 3100)
    plt.yticks(range(0, 3501, 500))
    plt.legend(loc='upper left', fontsize=11, framealpha=0.9)
    plt.tight_layout()

    figure_filename = f'heat_demand_graph_FR_{target_date.strftime("%d_%m_%Y")}.pdf'
    plt.savefig(figure_filename, bbox_inches='tight')
    plt.close()
