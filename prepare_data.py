import pandas as pd
import glob
import os

DATA_FOLDER = "data"
OUTPUT_FILE = "btc_real_data.csv"

# Alt klasörleri de tara
files = glob.glob(f"{DATA_FOLDER}/**/*.csv", recursive=True)
print(f"📁 {len(files)} adet CSV dosyası bulundu...")

if len(files) == 0:
    print("❌ CSV dosyası bulunamadı!")
    print("💡 ZIP dosyalarını çıkarttığından emin ol.")
    exit()

df_list = []
for f in sorted(files):
    try:
        # İlk satırı oku, başlık mı kontrol et
        first_row = pd.read_csv(f, nrows=1, header=None)
        has_header = first_row.iloc[0, 0] == "open_time" or str(first_row.iloc[0, 0]).isdigit() == False
        
        if has_header:
            # Başlıklı CSV (Binance yeni format)
            df = pd.read_csv(f, usecols=["open_time", "open", "high", "low", "close", "volume"])
            df = df.rename(columns={"open_time": "time"})
        else:
            # Başlıksız CSV (eski format)
            df = pd.read_csv(f, header=None, usecols=[0,1,2,3,4,5], 
                           names=["time","open","high","low","close","volume"])
        
        # Zamanı parse et
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        df_list.append(df)
        print(f"✅ {os.path.basename(f)} yüklendi ({len(df)} satır)")
        
    except Exception as e:
        print(f"⚠️ {f} atlandı: {e}")

if df_list:
    # Hepsini birleştir ve tarihe göre sırala
    df_all = pd.concat(df_list, ignore_index=True)
    df_all = df_all.sort_values("time").drop_duplicates(subset=["time"])
    df_all.set_index("time", inplace=True)
    
    # Kaydet
    df_all.to_csv(OUTPUT_FILE)
    
    print("\n" + "="*50)
    print("🎉 VERİ HAZIR!")
    print(f"📄 Dosya: '{OUTPUT_FILE}'")
    print(f"📊 Toplam satır: {len(df_all):,}")
    print(f"📅 Tarih aralığı: {df_all.index[0].date()} → {df_all.index[-1].date()}")
    print("="*50)
else:
    print("⚠️ Hiç veri birleştirilemedi.")