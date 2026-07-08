# Gerçekçi Dünya (Realistic World) — Minecraft 26.2 Fabric Modu

Dünya oluşturma ekranındaki **Dünya Türü** seçicisine (Varsayılan / Düz Dünya /
Geniş Biyomlar / Tek Biyom listesine) **"Gerçekçi Dünya"** adında, tamamen
matematiksel yöntemlerle üretilen yeni bir dünya türü ekler.

Mod tamamen **veri odaklıdır**: arazi, Minecraft'ın density function (yoğunluk
fonksiyonu) sistemi üzerinde matematiksel dönüşümlerle tanımlanır — Java kodu
içermez, bu sayede hafiftir ve sürüm geçişlerinde kolay güncellenir.

## Özellikler

### Dünya Türleri (Dünya Türü listesinde ayrı seçenekler)
Dünya oluşturma ekranındaki **Dünya Türü** düğmesinde artık dört seçenek var:
- **Gerçekçi Dünya** — bayrak mod; aşağıdaki tüm arazi, mağara, jeoloji ve
  özel biyom özelliklerini içerir.
- **Gerçekçi Adalar** — deniz seviyesi yükseltilmiş takımada dünyası; ovalar
  su altında, tepeler ada olur.
- **Gerçekçi Tek Kıta** — deniz seviyesi düşürülmüş; kıta sahanlığı açığa
  çıkar, geniş bağlantılı karalar.
- **Gerçekçi Kanyonlar** — `factor` genliği artırılmış keskin rölyef +
  düşük deniz seviyesi: derin kanyonlar ve dik zirveler.

### Özel Biyomlar (Gerçekçi Dünya'da)
Overworld biyom kaynağına vanilla biyomların yanına eklenir:
- **Yüksek Bozkır** (yüzey) — yüksek, kurak, açık renk otlak plato.
- **Sisli Vadi** (yüzey) — serin, nemli, gri gökyüzülü vadi (ladinli).
- **Volkanik Bölge** (yüzey) — sıcak, çorak, yağışsız kayalık.
- **Dev Sarkıt Mağarası** (mağara) — büyük dikit/sarkıtlarla dolu kaverna.
- **Kristal Mağara** (mağara) — mor/kristal tonlu yeraltı biyomu.

### Gerçekçi Cevher Dağılımı
Cevherler derinliğe/irtifaya göre yeniden dağıtılır (tüm dünya türlerinde):
demir dağlarda bol, bakır orta kuşakta, kömür yüzeye yakın, altın/kızıltaş/
lapis derinde, **elmas yalnızca derin bantta** (y < -32), zümrüt yüksek
dağlara özgü.

### Arazi
- **Kıta ölçeğinde kara parçaları** — kıtasallık/erozyon alanları 4× büyük
  dalga boylu noise ile üretilir; geniş okyanuslar, gerçekçi kıyı şeritleri.
- **Çizgisel sıradağlar** — ridge noise'un mutlak değer katlamaları (fold)
  tektonik görünümlü dağ zincirleri oluşturur; sivrilik (jaggedness) genliği
  %35 artırılmıştır.
- **Hipsometrik yükseklik dağılımı** — gerçek Dünya'daki gibi karaların çoğu
  alçak ova; zirveler nadir ve dramatiktir (taban ~y 260'a kadar).
  Okyanuslar kıta sahanlığından sonra 1.6× hızla derinleşir (taban ~y 14).
- **Derin nehir vadileri ve kanyonlar** — vanilla nehir matematiği korunur,
  erozyon spline'ı vadileri belirginleştirir.

### Mağaralar
- **Katedral boyutunda kavernalar** — peynir mağarası eşiği sabit 0.27 yerine
  derinliğe bağlı gradyandır (y=-64'te 0.05): derine indikçe salonlar devleşir.
- **Daha geniş ve yoğun tünel ağı** — spagetti/noodle tünel kalınlıkları
  artırılmıştır; katmanlar arası bağlantılı labirent.
- **Büyük mağara girişleri** — giriş eşiği 0.37 → 0.27.
- **Doğal sütunlar** — kavernalarda taş kolonlar daha sık oluşur.
- Su/lav gölleri (aquifer) ve cevher damarları (ore veins) vanilla gibi çalışır.

### Büyük Köy Güncellemesi
- **Çok daha büyük köyler** — jigsaw derinliği 6→7, merkezden azami uzaklık
  80→116 blok (codec üst sınırı): köyler belirgin biçimde daha geniş alana
  yayılır.
- **Planlı köy meydanı** — her köy 15×15 taş döşeli bir meydandan başlar:
  merkezi çeşme, köy çanı, pazar tezgâhları, fener direkleri, banklar.
  Meydandan **8 sokak çıkışı** (vanilla 3-4) köyü her yöne doğal biçimde
  dallandırır.
- **Özel binalar + vanilla evler bir arada** — ev havuzlarına üç yeni bina
  eklenir (vanilla evler aynen kalır):
  *Konak* (iki katlı, 4 yataklı), *Pazar* (yün tenteli açık çarşı),
  *Kulübe* (bahçeli, kompostorlu). Malzemeler biyoma uyar
  (meşe/akasya/ladin/kumtaşı); 5 köy biyomunun tamamı desteklenir.
- Zombi köyü varyantları ve vanilla çeşme/buluşma noktaları düşük
  ağırlıkla korunur; demir golem, kedi ve köylü yerleşimi vanilla
  kurallarıyla çalışır.

### Jeoloji ve yüzey
- **İrtifaya bağlı kar çizgisi** — y≈144'ten itibaren noise ile dalgalanan,
  y≥172'de kalıcı kar örtüsü; y>190'da buzul (packed ice) yamaları.
- **Falezler** — dik yamaçlarda çimen tutmaz, çıplak kaya görünür.
- **Katmanlı stratigrafi** — derinliğe göre bulanık sınırlı kalsit → andezit →
  granit → diyorit → tüf mercekleri.
- **Geniş kumsallar** — kıyı bandında (y 60–67) noise kapılı kum plajları,
  altında kumtaşı.

## Kurulum

1. Minecraft **26.2** için [Fabric Loader](https://fabricmc.net/use/installer/)
   (≥ 0.18.4) kurun.
2. [Fabric API](https://modrinth.com/mod/fabric-api)'nin 26.2 sürümünü
   (0.152.1+26.2 veya üstü) `mods/` klasörüne atın.
3. `dist/realisticworld-1.0.0+26.2.jar` dosyasını `mods/` klasörüne atın.
4. Oyunu açın → **Tek Oyunculu → Yeni Dünya Oluştur → Dünya sekmesi →
   Dünya Türü** düğmesine basarak **"Gerçekçi Dünya"** seçeneğine gelin →
   dünyayı oluşturun.

## Geliştirme

```bash
./tools/regen.sh --fetch   # tum worldgen verisini dogru sirada yeniden uret + dogrula
./build.sh                 # dist/ altina jar paketle
```

Üreteçler (sıra önemli — `tools/regen.sh` bunu uygular):
- `tools/generate.py` — arazi + mağara matematiği + ek dünya türleri
  (islands/pangaea/canyons); vanilla 26.2 worldgen'i temel alır.
- `tools/villages.py` — köy meydanı ve özel binaları NBT olarak sıfırdan üretir,
  jigsaw havuzlarını ve yapı tanımlarını günceller.
- `tools/ores.py` — cevher placed_feature'larını derinliğe göre yeniden dağıtır.
- `tools/biomes.py` — özel biyomları üretir ve bayrak preset'inin biyom
  kaynağını (vanilla + özel) **açık listeye** çevirir; **en son çalışmalıdır**.
- `tools/validate.py` — JSON şeması, referans bütünlüğü, NBT ve biyom tutarlılığı.
- `tools/refs/overworld_biome_parameters.json` — vanilla 26.2 overworld biyom
  parametre listesi (`gen-params` workflow'u üretir); özel biyom enjeksiyonunun
  temeli.

Uçtan uca doğrulama CI'da gerçek bir Fabric 26.2 sunucusu açıp preset'le chunk
üreterek yapılır (`.github/workflows/verify.yml`) — dünya oluşturma ekranını
kilitleyebilecek veri hataları burada yakalanır.
- Mod veri odaklı olduğu için jar, `src/main/resources` içeriğinin arşividir;
  Gradle/Loom gerekmez.

## Lisans

MIT
