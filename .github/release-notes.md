Dünya oluşturma ekranındaki **Dünya Türü** listesine **"Gerçekçi Dünya"** seçeneğini ekleyen, tamamen matematiksel dünya oluşumu yapan Fabric modu.

## Özellikler
- Kıta ölçeğinde kara parçaları, geniş okyanuslar, gerçekçi kıyılar
- Çizgisel sıradağlar, %35 daha sivri zirveler (~y 260'a kadar)
- Gerçekçi yükseklik dağılımı: çoğunlukla ova, nadir dramatik zirveler, derin okyanus tabanları
- Derinlere indikçe devleşen kavernalar, daha geniş tünel ağı, büyük mağara girişleri, doğal sütunlar
- İrtifaya bağlı kar çizgisi ve buzullar, dik yamaçlarda falezler, geniş kumsallar, katmanlı jeoloji
- **Büyük Köy Güncellemesi**: daha geniş köyler (derinlik 7, yarıçap 116), çeşmeli/çanlı/pazarlı planlı köy meydanı, meydandan 8 sokak çıkışı, biyoma uyumlu 3 özel bina (konak, pazar, kulübe) vanilla evlerle bir arada — 5 köy biyomunun tamamında

## v1.1.1 düzeltmesi
- **"Dünya Oluştur" ekranının sonsuza dek beklemesi giderildi.** Köy yapılarının merkezden azami uzaklığı 128 idi; Minecraft'ın kuralı bu değer + arazi uyarlama payını (12) 128 ile sınırlar, bu yüzden 5 köy yapısı da veri kaydına yüklenemiyor ve dünya ekranı "Hazırlanıyor"da asılıyordu. Değer geçerli üst sınır olan 116'ya çekildi. (Gerçek Fabric 26.2 sunucusuyla CI'da doğrulandı.)

## Kurulum
1. Minecraft **26.2** için [Fabric Loader](https://fabricmc.net/use/installer/) (≥ 0.18.4) kurun
2. [Fabric API](https://modrinth.com/mod/fabric-api) 0.152.1+26.2 (veya üstü) sürümünü `mods/` klasörüne atın
3. Aşağıdaki `realisticworld-*.jar` dosyasını indirip `mods/` klasörüne atın
4. Tek Oyunculu → Yeni Dünya Oluştur → **Dünya Türü → Gerçekçi Dünya**
