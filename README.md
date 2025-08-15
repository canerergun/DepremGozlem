# Deprem Gözlem Uygulaması



Deprem Gözlem, Türkiye'deki son deprem verilerini Kandilli Rasathanesi'nden otomatik olarak çeken, veritabanına kaydeden, analiz eden ve harita üzerinde görselleştiren bir masaüstü uygulamasıdır. PySide6 ile geliştirilmiştir ve tek bir Python dosyasında çalışacak şekilde tasarlanmıştır.



## Özellikler



* **Gerçek Zamanlı Veri**: Orhan Aydoğdu'nun API'si aracılığıyla Kandilli Rasathanesi'nden canlı deprem verilerini çeker.

* **Veritabanı Entegrasyonu**: Gelen veriler, yerel bir SQLite veritabanına (`deprem.db`) kaydedilir ve çevrimdışı erişime olanak tanır.

* **Çoklu Görünüm**:

    * **Ana Sayfa**: Genel istatistikleri ve en son deprem bilgilerini gösterir.

    * **Harita**: Folium kütüphanesi ile depremleri harita üzerinde görselleştirir. MarkerCluster ve HeatMap gibi farklı gösterim modları mevcuttur.

    * **Yakındaki Depremler**: Veritabanındaki son 200 depremi listeleyerek detaylı inceleme imkanı sunar. Deprem listesi CSV ve PDF formatında dışa aktarılabilir.

    * **Analizler**: Matplotlib ile deprem büyüklüğü, derinlik dağılımı ve günlük ortalama büyüklük gibi çeşitli analiz grafikleri oluşturur.

    * **Bina Riski Analizi**: Basit bir formüle dayalı olarak bina deprem riskini tahmin eder (yalnızca bilgilendirme amaçlıdır).

    * **Bilgi Merkezi**: Deprem öncesi, sırası ve sonrası için temel bilgileri içerir.

* **Bildirimler**: Belirlenen büyüklük eşiğini aşan depremler için sistem tepsisi bildirimi gönderir ve sesli uyarı verir.

* **Özelleştirme**: Ayarlar dosyası (`settings.json`) ile bildirim eşiği, otomatik yenileme süresi ve harita görünümü gibi parametreler yapılandırılabilir.

* **Tema Desteği**: Koyu ve açık tema seçenekleri mevcuttur.

* **Günlük Kaydı (Logging)**: Uygulama içindeki olayları, hataları ve API çağrılarını `app.log` dosyasına kaydeder.



## Gereksinimler



* Python 3.12+

* `PySide6`

* `requests`

* `folium` (Harita için)

* `matplotlib` (Analiz grafikleri için)

* `reportlab` (PDF dışa aktarımı için)



## Kurulum



Gerekli kütüphaneleri yüklemek için:



```bash

pip install PySide6 requests folium matplotlib reportlab

```

