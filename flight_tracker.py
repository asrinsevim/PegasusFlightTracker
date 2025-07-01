import asyncio
import re
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.async_api import async_playwright
import pandas as pd
from datetime import timedelta

# --- KULLANICI AYARLARI ---

# 1. Uçuş Arama Ayarları
NEREDEN = "İstanbul Tümü"
NEREYE = "Tiran"
GİDİS_PORT_KODU = "IST_SAW"
DONUS_PORT_KODU = "TIA"
SEYAHAT_SURELERI = [7, 8, 9] # İncelenecek seyahat süreleri (gün)

# 2. Dosya İsimleri (Tüm script bu isimleri kullanacak)
GİDİS_CSV = 'gidis_fiyatlari.csv'
DONUS_CSV = 'donus_fiyatlari.csv'
ARSIV_CSV = 'onceki_sonuclar.csv'

# 3. E-POSTA AYARLARI
# UYARI: Güvenliğiniz için buraya gerçek şifrenizi DEĞİL, Google'dan alacağınız 16 haneli "Uygulama Şifresini" girin.
GONDEREN_EPOSTA = "denemecan33@gmail.com"
ALICI_EPOSTA = ["asrnsevim@hotmail.com", "bcaliskan4691@gmail.com"] # Raporu alacak kişisel e-posta adresleri
EPOSTA_SIFRESI = "wgda jdru ylqh ujst"  # Robot mail için oluşturulan 16 haneli Uygulama Şifresi

SMTP_SUNUCU = "smtp.gmail.com"
SMTP_PORT = 587

# ==============================================================================
# BÖLÜM 1: VERİ ÇEKME (SCRAPING) FONKSİYONLARI
# ==============================================================================

async def scrape_calendar_prices(page):
    print("Takvimdeki fiyatlar çekilmeye başlanıyor...")
    tum_fiyatlar = []
    islenmis_tarihler = set()
    DEFAULT_TIMEOUT = 20000

    print("\nAdım 1: İlk görünen ayların taranması...")
    try:
        await page.locator(".flatpickr-current-month").first.wait_for(timeout=DEFAULT_TIMEOUT)
        await page.wait_for_timeout(1000)
        ay_basliklari = await page.locator(".flatpickr-current-month").all_inner_texts()
        price_days = await page.locator("span.flatpickr-day.DateInput__has-price:visible").all()
        for day_element in price_days:
            tarih_str = await day_element.get_attribute("aria-label")
            if tarih_str and tarih_str not in islenmis_tarihler:
                fiyat_str = await day_element.locator("span.DateInput__day-price").inner_text()
                fiyat_temiz = re.sub(r'\s+', '', fiyat_str) + " TL"
                tum_fiyatlar.append({"Tarih": tarih_str, "Fiyat": fiyat_temiz})
                islenmis_tarihler.add(tarih_str)
    except Exception as e:
        print(f"İlk ayları tararken bir sorun oluştu: {e}")

    dongu_sayisi = 1
    for i in range(dongu_sayisi):
        try:
            print(f"\nAdım {i + 2}: Sonraki aylara geçiliyor...")
            mevcut_son_ay = (await page.locator(".flatpickr-current-month").all_inner_texts())[-1]
            next_month_button = page.locator(".flatpickr-calendar .DateInput__next-arrow:visible")
            await next_month_button.click()
            await page.wait_for_timeout(500)
            await next_month_button.click()
            print("Yeni ayların yüklenmesi bekleniyor...")
            await page.locator(f".flatpickr-current-month:text-matches('{mevcut_son_ay}')").last.wait_for(state='hidden', timeout=DEFAULT_TIMEOUT)
            await page.wait_for_timeout(500)
            ay_basliklari = await page.locator(".flatpickr-current-month").all_inner_texts()
            price_days_yeni = await page.locator("span.flatpickr-day.DateInput__has-price:visible").all()
            for day_element in price_days_yeni:
                tarih_str = await day_element.get_attribute("aria-label")
                if tarih_str and tarih_str not in islenmis_tarihler:
                    fiyat_str = await day_element.locator("span.DateInput__day-price").inner_text()
                    fiyat_temiz = re.sub(r'\s+', '', fiyat_str) + " TL"
                    tum_fiyatlar.append({"Tarih": tarih_str, "Fiyat": fiyat_temiz})
                    islenmis_tarihler.add(tarih_str)
        except Exception as e:
            print(f"{i + 2}. adımı tararken bir sorun oluştu: {e}")
            continue
    return tum_fiyatlar

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, slow_mo=50) # headless=True daha hızlı çalışır
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        try:
            print("Pegasus web sitesi açılıyor...")
            await page.goto("https://www.flypgs.com/")
            try:
                await page.get_by_role("button", name="Kabul Et").click(timeout=5000)
                print("Çerez pop-up'ı kabul edildi.")
            except Exception:
                print("Çerez pop-up'ı çıkmadı, devam ediliyor.")
            
            print("Uçuş bilgileri giriliyor...")
            await page.locator("#fromWhere").click()
            await page.locator("#fromWhere").fill(NEREDEN)
            await page.locator(f'.tstnm_fly_search_tab_1_departure_list_item[data-port-code="{GİDİS_PORT_KODU}"]').click()
            await page.locator("#toWhere").click()
            await page.locator("#toWhere").fill(NEREYE)
            await page.locator(f'.tstnm_fly_search_tab_1_arrival_list_item[data-port-code="{DONUS_PORT_KODU}"]').click()
            
            print("\n--- GİDİŞ FİYATLARI TARAMASI ---")
            gidis_fiyat_verisi = await scrape_calendar_prices(page)
            if gidis_fiyat_verisi:
                pd.DataFrame(gidis_fiyat_verisi).drop_duplicates().to_csv(GİDİS_CSV, index=False, encoding='utf-8-sig')
                print(f"\n===> Gidiş fiyatları '{GİDİS_CSV}' dosyasına kaydedildi.")
            else:
                print("HATA: Hiçbir gidiş fiyatı verisi çekilemedi.")
                return False

            await page.keyboard.press("Escape")
            await page.wait_for_timeout(1000)
            
            print("\n--- DÖNÜŞ FİYATLARI TARAMASI ---")
            await page.locator('.tstnm_fly_search_tab_1_return_date_area').click()
            donus_fiyat_verisi = await scrape_calendar_prices(page)
            if donus_fiyat_verisi:
                pd.DataFrame(donus_fiyat_verisi).drop_duplicates().to_csv(DONUS_CSV, index=False, encoding='utf-8-sig')
                print(f"\n===> Dönüş fiyatları '{DONUS_CSV}' dosyasına kaydedildi.")
            else:
                print("HATA: Hiçbir dönüş fiyatı verisi çekilemedi.")
                return False
            return True
        except Exception as e:
            print(f"ANA VERİ ÇEKME İŞLEMİ SIRASINDA BİR HATA OLUŞTU: {e}")
            await page.screenshot(path="hata_ekrani.png")
            return False
        finally:
            print("Tarayıcı kapatılıyor...")
            await context.close()
            await browser.close()

# ==============================================================================
# BÖLÜM 2: ANALİZ VE RAPORLAMA FONKSİYONLARI
# ==============================================================================

def clean_price(price):
    if isinstance(price, str):
        price = price.replace('.', '').replace(' TL', '').strip()
    return int(price)

def find_best_flight_combinations(departure_file, return_file, trip_durations):
    try:
        df_gidis = pd.read_csv(departure_file); df_donus = pd.read_csv(return_file)
    except FileNotFoundError as e:
        print(f"Hata: Analiz için gereken CSV dosyası bulunamadı -> {e}"); return None
    
    turkish_to_english_months = {
        'Ocak': 'January', 'Şubat': 'February', 'Mart': 'March', 'Nisan': 'April', 'Mayıs': 'May',
        'Haziran': 'June', 'Temmuz': 'July', 'Ağustos': 'August', 'Eylül': 'September',
        'Ekim': 'October', 'Kasım': 'November', 'Aralık': 'December'
    }
    df_gidis['Tarih_Eng'] = df_gidis['Tarih'].replace(turkish_to_english_months, regex=True)
    df_donus['Tarih_Eng'] = df_donus['Tarih'].replace(turkish_to_english_months, regex=True)
    date_format = "%B %d, %Y"
    df_gidis['Tarih'] = pd.to_datetime(df_gidis['Tarih_Eng'], format=date_format, errors='coerce')
    df_donus['Tarih'] = pd.to_datetime(df_donus['Tarih_Eng'], format=date_format, errors='coerce')
    df_gidis['Fiyat'] = df_gidis['Fiyat'].apply(clean_price)
    df_donus['Fiyat'] = df_donus['Fiyat'].apply(clean_price)
    df_gidis.dropna(subset=['Tarih', 'Fiyat'], inplace=True); df_donus.dropna(subset=['Tarih', 'Fiyat'], inplace=True)
    
    uygun_kombinasyonlar = []
    for _, gidis_ucusu in df_gidis.iterrows():
        for sure in trip_durations:
            hedef_donus_tarihi = gidis_ucusu['Tarih'] + timedelta(days=sure)
            uygun_donusler = df_donus[df_donus['Tarih'] == hedef_donus_tarihi]
            for _, donus_ucusu in uygun_donusler.iterrows():
                uygun_kombinasyonlar.append({
                    'Gidiş Tarihi': gidis_ucusu['Tarih'].strftime('%d-%m-%Y'),
                    'Dönüş Tarihi': hedef_donus_tarihi.strftime('%d-%m-%Y'),
                    'Seyahat Süresi (Gün)': sure,
                    'Toplam Fiyat (TL)': gidis_ucusu['Fiyat'] + donus_ucusu['Fiyat']
                })
    if not uygun_kombinasyonlar:
        print("Analiz sonucu: Belirtilen kriterlere uygun hiçbir uçuş kombinasyonu bulunamadı.")
        return None
    return pd.DataFrame(uygun_kombinasyonlar).sort_values(by='Toplam Fiyat (TL)', ascending=True)

def compare_and_report(yeni_sonuclar, arsiv_dosyasi):
    yeni_sonuclar['Gidis_Tarihi_Obj'] = pd.to_datetime(yeni_sonuclar['Gidiş Tarihi'], format='%d-%m-%Y')
    yeni_sonuclar['Gidis_Ayi'] = yeni_sonuclar['Gidis_Tarihi_Obj'].dt.strftime('%Y-%m')
    yeni_top_10_liste = yeni_sonuclar.groupby('Gidis_Ayi').head(10)
    
    if not os.path.exists(arsiv_dosyasi):
        print("Arşiv dosyası bulunamadı. Bu ilk çalıştırma. Güncel liste arşivleniyor.")
        yeni_top_10_liste.drop(columns=['Gidis_Tarihi_Obj', 'Gidis_Ayi']).to_csv(arsiv_dosyasi, index=False)
        rapor_df = yeni_top_10_liste.rename(columns={'Toplam Fiyat (TL)': 'Toplam Fiyat (TL)_yeni'})
        rapor_df['Durum'] = "İlk Kayıt"
        return rapor_df

    eski_top_10_liste = pd.read_csv(arsiv_dosyasi)
    karsilastirma_df = pd.merge(yeni_top_10_liste, eski_top_10_liste, on=['Gidiş Tarihi', 'Dönüş Tarihi'], how='outer', suffixes=('_yeni', '_eski'))
    karsilastirma_df = karsilastirma_df.sort_values(by=['Gidis_Ayi', 'Toplam Fiyat (TL)_yeni']).reset_index(drop=True)
    
    durumlar = []
    for _, row in karsilastirma_df.iterrows():
        eski_fiyat, yeni_fiyat = row['Toplam Fiyat (TL)_eski'], row['Toplam Fiyat (TL)_yeni']
        if pd.isna(eski_fiyat): durumlar.append(f"YENİ FIRSAT!")
        elif pd.isna(yeni_fiyat): durumlar.append(f"Listeden Çıktı (Eski Fiyat: {int(eski_fiyat)} TL)")
        elif yeni_fiyat < eski_fiyat: durumlar.append(f"FİYAT DÜŞTÜ! (Eski: {int(eski_fiyat)} TL)")
        elif yeni_fiyat > eski_fiyat: durumlar.append(f"Fiyat Arttı (Eski: {int(eski_fiyat)} TL)")
        else: durumlar.append("Aynı Fiyat")
        
    karsilastirma_df['Durum'] = durumlar
    yeni_top_10_liste.drop(columns=['Gidis_Tarihi_Obj', 'Gidis_Ayi']).to_csv(arsiv_dosyasi, index=False)
    print(f"Arşiv dosyası '{arsiv_dosyasi}' güncellendi.")
    return karsilastirma_df

def send_email_report(report_df):
    deals = report_df[report_df['Durum'].str.contains('YENİ FIRSAT|FİYAT DÜŞTÜ', regex=True, na=False)]
    if deals.empty:
        print("Yeni veya fiyatı düşen bir uçuş bulunamadı. E-posta gönderilmeyecek.")
        return
        
    html = """
    <html><head><style>
      body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; }
      h2, h3 { color: #2E86C1; border-bottom: 2px solid #f2f2f2; padding-bottom: 5px;}
      table { border-collapse: collapse; width: 100%; margin: 20px 0; font-size: 14px; }
      th, td { border: 1px solid #dddddd; text-align: left; padding: 12px; }
      tr:nth-child(even) { background-color: #f2f2f2; }
      th { background-color: #4CAF50; color: white; }
      .status-new { color: #0000FF; font-weight: bold; }
      .status-dropped { color: #008000; font-weight: bold; }
    </style></head><body>
      <h2>&#9992;&#65039; Tiran Uçuş Fiyatı Alarm Raporu</h2>
    """
    if not deals.empty:
        html += "<h3>Fırsat Tablosu (Yeni veya Fiyatı Düşenler)</h3>"
        deals_to_print = deals.rename(columns={'Toplam Fiyat (TL)_yeni': 'Yeni Fiyat (TL)'})
        deals_html_table = deals_to_print[['Gidiş Tarihi', 'Dönüş Tarihi', 'Yeni Fiyat (TL)', 'Durum']].to_html(index=False, escape=False, na_rep="-")
        html += deals_html_table
    
    full_list_df = report_df[report_df['Toplam Fiyat (TL)_yeni'].notna()].copy()
    if not full_list_df.empty:
        html += "<br><hr><br><h2>Tüm Ayların En Uygun 10 Uçuşu (Güncel Tam Liste)</h2>"
        for ay_kodu, grup in full_list_df.groupby('Gidis_Ayi'):
            gidis_ayi_numarasi = ay_kodu.split('-')[1]
            html += f"<h3>Gidiş Ayı {gidis_ayi_numarasi} Olanlar</h3>"
            grup_to_print = grup[['Gidiş Tarihi', 'Dönüş Tarihi', 'Seyahat Süresi (Gün)_yeni', 'Toplam Fiyat (TL)_yeni', 'Durum']].rename(columns={
                'Seyahat Süresi (Gün)_yeni': 'Süre (Gün)', 'Toplam Fiyat (TL)_yeni': 'Fiyat (TL)'
            })
            html += grup_to_print.to_html(index=False, escape=False, na_rep="-") + "<br>"
            
    html += """<p style="font-size:small; color:grey;">Bu e-posta, Python script'iniz tarafından otomatik olarak gönderilmiştir.</p></body></html>"""

    message = MIMEMultipart("alternative")
    message["Subject"] = "Tiran FlightTracker: Yeni Fırsatlar Bulundu!"
    message["From"] = GONDEREN_EPOSTA
    message["To"] = ", ".join(ALICI_EPOSTA)
    message.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(SMTP_SUNUCU, SMTP_PORT) as server:
            server.starttls()
            server.login(GONDEREN_EPOSTA, EPOSTA_SIFRESI)
            server.sendmail(GONDEREN_EPOSTA, ALICI_EPOSTA, message.as_string())
            print(f"Detaylı raporu içeren e-posta başarıyla gönderildi! Alıcılar: {', '.join(ALICI_EPOSTA)}")
    except Exception as e:
        print(f"E-POSTA GÖNDERME HATASI: {e}")
        print("LÜTFEN DİKKAT: E-posta ayarlarınızı (özellikle şifre) kontrol edin. Gmail için normal şifre yerine 'Uygulama Şifresi' kullanmanız gerekmektedir.")

# ==============================================================================
# BÖLÜM 3: ANA ÇALIŞTIRMA MANTIĞI
# ==============================================================================

def main():
    print("="*50)
    print("UÇUŞ OTOMASYONU BAŞLATILIYOR")
    print("="*50)

    # 1. Adım: Veri Çekme
    print("\n[AŞAMA 1/3] Güncel uçuş verileri web sitesinden çekiliyor...")
    scraping_basarili = asyncio.run(run_scraper())

    if not scraping_basarili:
        print("\n[HATA] Veri çekme işlemi başarısız oldu. Script durduruluyor.")
        return

    # 2. Adım: Fiyat Kombinasyonlarını Bulma
    print("\n[AŞAMA 2/3] Çekilen verilerle en uygun uçuş kombinasyonları hesaplanıyor...")
    tum_sonuclar = find_best_flight_combinations(GİDİS_CSV, DONUS_CSV, SEYAHAT_SURELERI)

    if tum_sonuclar is None:
        print("\n[HATA] Uçuş kombinasyonları hesaplanamadı. Script durduruluyor.")
        return

    # 3. Adım: Karşılaştırma, Raporlama ve E-posta
    print("\n[AŞAMA 3/3] Yeni sonuçlar arşivle karşılaştırılıyor ve rapor oluşturuluyor...")
    rapor_df = compare_and_report(tum_sonuclar, ARSIV_CSV)
    
    print("\nKarşılaştırma raporu oluşturuldu. Ekrana yazdırılıyor...")
    print("="*80)
    rapor_df_print = rapor_df.copy()
    rapor_df_print['Toplam Fiyat (TL)'] = rapor_df_print['Toplam Fiyat (TL)_yeni'].fillna(rapor_df_print['Toplam Fiyat (TL)_eski'])
    for ay_kodu, grup in rapor_df_print.groupby('Gidis_Ayi'):
        if pd.isna(ay_kodu): continue
        gidis_ayi_numarasi = str(ay_kodu).split('-')[1]
        print(f"--- Gidiş Ayı {gidis_ayi_numarasi} Olanlar ---\n")
        grup_to_print = grup[['Gidiş Tarihi', 'Dönüş Tarihi', 'Toplam Fiyat (TL)', 'Durum']]
        print(grup_to_print.to_string(index=False))
        print("\n" + "-"*50 + "\n")
    
    print("E-posta gönderim süreci başlatılıyor...")
    send_email_report(rapor_df)
    
    print("\n="*5)
    print("OTOMASYON TAMAMLANDI")
    print("="*5)


if __name__ == "__main__":
    main()