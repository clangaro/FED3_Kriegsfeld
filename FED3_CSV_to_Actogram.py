import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import glob

# ==============================================================================
# --- CONFIGURATION ---
# ==============================================================================
# Point this to the folder containing all the CSV files you want to stitch together
INPUT_FOLDER = "/Volumes/FED3/Analysis"  
ANIMAL_ID = "FED3 Test"                       # Used for the AWD header and plot title

# Actogram Aesthetic Options
LIGHT_START_HOUR = 7.0    # Hour lights turn ON (e.g., 10.0 = 10:00 AM)
DARK_START_HOUR = 19.0    # Hour lights turn OFF (e.g., 22.0 = 10:00 PM)
LIGHT_COLOR = "lemonchiffon"
DARK_COLOR = "lightgray"
# ==============================================================================

def load_and_stitch_csvs(folder_path):
    """
    Scans a folder for all CSV files, extracts timestamps, combines them 
    chronologically, and removes any duplicate timestamps.
    """
    search_path = os.path.join(folder_path, "*.CSV")
    csv_files = glob.glob(search_path)
    
    if not csv_files:
        raise FileNotFoundError(f"❌ No CSV files found in folder: {folder_path}")
        
    print(f"🔍 Found {len(csv_files)} CSV files. Stitching them chronologically...")
    
    all_data = []
    
    for file in csv_files:
        try:
            df = pd.read_csv(file)
            # Find the timestamp column dynamically
            date_col = [c for c in df.columns if 'MM:DD:YYYY' in c or 'time' in c.lower()]
            if not date_col:
                print(f"⚠️ Skipping {os.path.basename(file)}: No timestamp column found.")
                continue
                
            # Standardize columns for merging
            df['Timestamp'] = pd.to_datetime(df[date_col[0]])
            df['Event'] = 1
            all_data.append(df[['Timestamp', 'Event']])
        except Exception as e:
            print(f"⚠️ Error reading {os.path.basename(file)}: {e}")

    if not all_data:
        raise ValueError("❌ No valid data could be extracted from the CSV files.")

    # Combine all files into one master dataframe
    combined_df = pd.concat(all_data, ignore_index=True)
    
    # Sort chronologically (equivalent to arrange(datetime) in R)
    combined_df.sort_values('Timestamp', inplace=True)
    
    # Drop exact overlapping duplicates (equivalent to distinct() in R)
    combined_df.drop_duplicates(subset=['Timestamp'], inplace=True)
    
    return combined_df

def csv_to_clocklab_awd(combined_df, animal_id, bin_freq='1min'):
    """
    Takes the combined chronological data, bins it into 1-minute blocks,
    and saves it to a ClockLab AWD file.
    """
    # Establish a perfect calendar-aligned grid from 00:00:00 of Day 1
    start_date = combined_df['Timestamp'].min().normalize()
    end_date = combined_df['Timestamp'].max().normalize() + pd.Timedelta(days=1)
    
    full_time_grid = pd.date_range(start=start_date, end=end_date - pd.Timedelta(minutes=1), freq=bin_freq)
    
    # Group into 1-minute bins and count the feeding events
    df_binned = combined_df.set_index('Timestamp').resample(bin_freq).sum()
    df_binned = df_binned.reindex(full_time_grid, fill_value=0)
    
    epoch_code = 4  # 1-minute bins
    awd_filename = f"{animal_id}_combined_clocklab.awd"
    
    print(f"💾 Writing stitched ClockLab AWD file to '{awd_filename}'...")
    print(f"📅 Covered Date Range: {start_date.strftime('%Y-%m-%d')} to {combined_df['Timestamp'].max().strftime('%Y-%m-%d')}")
    
    with open(awd_filename, 'w') as f:
        f.write(f"{animal_id}\n")                              
        f.write(f"{start_date.strftime('%d-%b-%Y')}\n")        
        f.write(f"{start_date.strftime('%H:%M')}\n")           
        f.write(f"{epoch_code}\n")                             
        f.write("0\n")                                         
        f.write("0\n")                                         
        f.write("0\n")                                         
        
        for value in df_binned['Event']:
            f.write(f"{int(value)}\n")
            
    print("✅ AWD file generation complete!")
    return awd_filename, start_date, end_date, df_binned['Event'].values

def generate_double_plot_actogram(values, start_date, end_date, animal_id):
    """Generates a professional 48-hour double-plotted actogram from the array."""
    print("📈 Generating 48-hour double-plotted actogram...")
    
    bins_per_day = 1440
    total_days = int(len(values) / bins_per_day)
    
    if total_days < 1:
        print("❌ Error: Not enough data to generate an actogram.")
        return

    daily_matrix = values.reshape(total_days, bins_per_day)
    
    # Dynamic size matching row count beautifully
    fig, axes = plt.subplots(nrows=total_days, ncols=1, figsize=(8, 0.28 * total_days), sharex=True)
    if total_days == 1:
        axes = [axes]
        
    plt.subplots_adjust(hspace=0.0) 
    
    minutes_axis_48h = np.linspace(0, 48, bins_per_day * 2, endpoint=False)

    for i in range(total_days):
        ax = axes[i]
        current_date = start_date + pd.Timedelta(days=i)
        
        # Double plotting logic
        left_side_data = daily_matrix[i]
        right_side_data = daily_matrix[i+1] if i < (total_days - 1) else np.zeros(bins_per_day)
        combined_48h_data = np.concatenate([left_side_data, right_side_data])
        
        # 24h panel 1 shading
        ax.axvspan(0, LIGHT_START_HOUR, color=DARK_COLOR, alpha=0.35, lw=0)
        ax.axvspan(LIGHT_START_HOUR, DARK_START_HOUR, color=LIGHT_COLOR, alpha=0.45, lw=0)
        ax.axvspan(DARK_START_HOUR, 24, color=DARK_COLOR, alpha=0.35, lw=0)
        
        # 24h panel 2 shading
        ax.axvspan(24, 24 + LIGHT_START_HOUR, color=DARK_COLOR, alpha=0.35, lw=0)
        ax.axvspan(24 + LIGHT_START_HOUR, 24 + DARK_START_HOUR, color=LIGHT_COLOR, alpha=0.45, lw=0)
        ax.axvspan(24 + DARK_START_HOUR, 48, color=DARK_COLOR, alpha=0.35, lw=0)
        
        # Plot bars
        ax.fill_between(minutes_axis_48h, 0, combined_48h_data, color='black', step='mid', lw=0.5)
        
        ax.set_xlim(0, 48)
        ax.set_ylim(0, max(values).max() if max(values).max() > 0 else 1)
        ax.set_yticks([])
        
        ax.set_ylabel(current_date.strftime('%d-%m-%Y'), rotation=0, 
                      labelpad=45, ha='right', va='center', fontsize=8)
        
        for spine in ['top', 'right', 'left', 'bottom']:
            ax.spines[spine].set_visible(False)

    axes[-1].spines['bottom'].set_visible(True)
    axes[-1].spines['bottom'].set_color('black')
    
    ticks_48h = list(range(0, 25, 2)) + list(range(2, 25, 2))
    tick_positions = list(range(0, 25, 2)) + list(range(26, 49, 2))
    
    axes[-1].set_xticks(tick_positions)
    axes[-1].set_xticklabels(ticks_48h, fontsize=8)
    axes[-1].set_xlabel('Time of Day (h)', fontsize=10, labelpad=8)
    
    fig.suptitle(f"{animal_id} - Continuous Actogram", fontsize=12, fontweight='bold', y=0.98)
    
    output_png = f"actogram_{animal_id}_stitched.png"
    plt.savefig(output_png, dpi=600, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"🎉 Success! Beautiful stitched actogram saved as '{output_png}'")

if __name__ == "__main__":
    if not os.path.exists(INPUT_FOLDER):
        print(f"❌ Error: The folder path '{INPUT_FOLDER}' does not exist.")
    else:
        try:
            combined_data = load_and_stitch_csvs(INPUT_FOLDER)
            awd_file, start_dt, end_dt, binned_values = csv_to_clocklab_awd(combined_data, ANIMAL_ID)
            generate_double_plot_actogram(binned_values, start_dt, end_dt, ANIMAL_ID)
        except Exception as e:
            print(f"❌ Pipeline failed: {e}")