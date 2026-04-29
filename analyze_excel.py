import pandas as pd

def analyze_excel():
    excel_file = r"c:\Users\shraddha.more\Downloads\MAHANET-Inward Outward Report-28-Apr-2026.xlsx"
    
    try:
        # Read Excel file
        excel_data = pd.read_excel(excel_file, sheet_name=None)
        
        print(f"Available sheets: {list(excel_data.keys())}")
        
        for sheet_name, df in excel_data.items():
            print(f"\n=== Sheet: {sheet_name} ===")
            print(f"Shape: {df.shape}")
            print(f"Columns: {list(df.columns)}")
            
            # Show first few rows
            print("\nFirst 3 rows:")
            print(df.head(3).to_string())
            
            # Check if first row contains headers
            print("\nFirst row values:")
            print(df.iloc[0].to_dict() if len(df) > 0 else "No data")
            
    except Exception as e:
        print(f"Error analyzing Excel: {e}")

if __name__ == "__main__":
    analyze_excel()
