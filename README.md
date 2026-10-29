Multi Library — Oyun Launcher (Windows)

Windows için kişisel oyun kütüphanesi ve launcher. Steam, Epic, EA app, Xbox ve Riot'ta kurulu oyunlarını tek yerden listeler, başlatır, oynama süreni takip eder; kapak, arka plan, ikon, fragman ve müziklerini otomatik bulmaya çalışır.

Özellikler





Dosya gezgini tarzı kütüphane: Oyunları satır satır (Ad, Değiştirme tarihi, Tür, Boyut) gösterir; seçili oyunun kapağı ve bilgileri sağ panelde, arka planda duvar kağıdı olarak görünür.



Kapak ızgarası: İstersen klasik kapak görünümüne geçebilirsin.



Kumanda desteği: Xbox ya da uyumlu kumanda ile tam gezinme; ana menüde de çalışır.



Tam ekran / dikey monitör: Kumanda ile açılınca ikinci (dikey) monitörde açılabilir.



F7 ve Xbox rehber düğmesi: Launcher'ı her yerden açar; açıksa tekrar basınca kapatır.



Oyun takibi: Oynama süresi, başlatma sayısı, son oynanma.



Otomatik kurulum: Kapak, arka plan, ikon, fragman (yt-dlp ile) ve oyun müziği indirme. Görsel aramak için isteğe bağlı Google Custom Search anahtarı.



Müzik çalar: Oyun müzikleri, sıra, ses kontrolü.



Görünüm: Tema rengi, cam panel saydamlığı, genel parlaklık, yazı boyutu.



Telefondan kumanda (isteğe bağlı): Aynı Wi-Fi üzerinde yerel web arayüzü.

Gereksinimler





Windows 10 / 11



Python 3.13 (https://www.python.org/downloads/)



Bağımlılıklar: requirements.txt içinde

Kurulum





Bu depoyu indir ya da klonla. Önerilen klasör: C:\Launcher



Bağımlılıkları kur:

 py -3.13 -m pip install -r requirements.txt



Launcher'ı çalıştır:

 py -3.13 launcher.py

 ya da Oyun Launcher.bat dosyasına çift tıkla.



(İsteğe bağlı) F7 / Xbox kısayolu için kisayol_dinleyici.pyw dosyasını çalıştır. Bilgisayar açılınca kendiliğinden başlasın istersen Win+R → shell:startup ile açılan klasöre kısayolunu koy.

Kullanım







İşlem



Klavye



Kumanda





Gezin



Ok tuşları



Sol çubuk / yön tuşları





Oyunu başlat



Enter / çift tık



A





Menü



Esc



Start / Y





Müzik



—



X (oynat/duraklat), LB/RB (şarkı)





Ses



—



LT / RT





Tam ekran



F11



Back

Oyun ekle: sağ üstteki Oyun ekle düğmesi ya da Ayarlar > Mağaza oyunlarını tara.

Notlar ve sınırlar





Launcher oyun kurmaz; Steam, Epic, EA app, Xbox ya da Riot'ta kurulu oyunları listeler ve başlatır.



Otomatik kapak / arka plan / fragman indirme internet bağlantısı ister ve sitelerin kurallarına bağlıdır; her oyunda sonuç garanti değildir.



Görsel arama için kendi Google Custom Search API anahtarını ve arama motoru kimliğini (gcs_key, gcs_cx) launcher_config.json içine girmen gerekir. Anahtarı kimseyle paylaşma.



Xbox rehber düğmesini Steam Input gibi programlar yakalayabilir; bu durumda kısayol çalışmayabilir.

Dosyalar





launcher.py — ana uygulama (arayüz, kütüphane, ayarlar)



launcher_vfx.py — görsel efektler (cam paneller, animasyonlar, başlatma geçişi, yazı tipi)



launcher_extras.py — mağaza oyunlarını otomatik bulma (Steam / Epic / EA app / Riot / Xbox), Windows ile başlatma, oyun başlatma ve izleme



launcher_features.py — yapılandırma yedeği, telefondan kumanda (yerel web sunucusu), boşta kalma ekranı



kisayol_dinleyici.pyw — F7 ve Xbox rehber düğmesi dinleyicisi



Oyun Launcher.bat — çift tıkla başlatma kısayolu



requirements.txt — Python bağımlılıkları

İsteğe bağlı: Yazı tipi için fonts klasörüne Inter yazı tipi konabilir; telefondan kumanda için QR kodu gösterilecekse pip install qrcode.

Yapılandırma dosyası (launcher_config.json) ilk çalıştırmada oluşur ve kişisel verilerini içerir; depoya eklenmez (.gitignore ile dışlanmıştır).

Lisans

Belirtilmedi — kullanım koşulları için sahibine danış.
