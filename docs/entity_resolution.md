# Entity Resolution ve Canonicalization (Gün 20)

Bu aşama, Gün 19 `entities.jsonl` kayıtlarını değişmeden girdi kabul eder ve Gün 18 graph
kimlik kurallarına uygun canonical entity kayıtları üretir. Chunking, embedding, Qdrant,
retrieval ve Neo4j katmanlarına yazmaz.

## Tasarım ilkeleri

- Normalizasyon entity tipine özeldir; tek başına isim benzerliği otomatik birleşme nedeni
  değildir.
- `EXACT_MATCH` ve `HIGH_CONFIDENCE_MATCH` otomatik birleştirilir.
- `REVIEW_REQUIRED` ayrı canonical entity olarak kalır ve önerilen aday denetim kaydında
  gösterilir.
- `DIFFERENT_ENTITY` birleştirilmez.
- Canonical ID; entity tipi, normalize ad ve gerekli şirket/dönem/rapor bağlamından
  deterministik üretilir. Girdi sırası sonucu değiştirmez.
- Aynı temel ID'ye sahip fakat birleşmesi güvenli olmayan kayıtlar `:variant:<digest>`
  ekiyle ayrı tutulur.

## Normalizasyon ve bağlam kuralları

| Tip | Ad normalizasyonu | Otomatik eşleşme için bağlam | Birleşmeyi engelleyen örnek |
|---|---|---|---|
| Company | ticker, yasal unvan ve `config/companies.yaml` alias kayıtları | Güvenilir alias registry aynı ticker'a inmeli | Farklı ticker veya yalnız fuzzy ad |
| Person | unvanları kaldırma, Türkçe karakter/case normalizasyonu | Aynı şirket; fuzzy eşleşmede aynı rapor veya yıl | Farklı şirket, eksik şirket bağlamı |
| Product | noktalama, case ve Türkçe karakter normalizasyonu | Aynı şirket ve aynı model kodu veya rapor | Çelişen model numarası |
| Sector | kontrollü sektör eşanlamlı sözlüğü | Aynı normalize sektör veya sınıflandırma kodu | Çelişen sınıflandırma kodu |
| FinancialMetric | kontrollü metrik sözlüğü (`ciro`, `hasılat`, `revenue` vb.) | Şirket, dönem, kapsam, birim, rapor ve değer | Farklı dönem/rapor; aynı bağlamda farklı değer incelemeye gider |

Kararlarda ayrıca rapor yılı, `source_report_id`, tarih, kapsam, birim, model kodları ve
evidence metninin token örtüşmesi saklanır. Evidence örtüşmesi destekleyici sinyaldir;
tek başına birleşme yaptırmaz.

## Makine tarafından okunabilir çıktılar

`EntityResolutionPipeline(output_dir).run(entities_path)` aşağıdaki dosyaları atomik
olarak üretir:

- `canonical_entities.jsonl`: canonical ID, tip, ad, özellikler, alias listesi, kaynak
  entity/chunk/rapor kimlikleri, yıllar, evidence örnekleri ve ortalama confidence.
- `aliases.jsonl`: her kaynak mention için canonical hedef, eşleşme sınıfı, otomatik
  birleşme durumu, inceleme adayı ve provenance.
- `resolution_decisions.jsonl`: karşılaştırılan her aday çifti için skorlar, olumlu
  sinyaller, çatışmalar, gerekçe, birleşme kararı ve iki canonical ID.
- `metrics.json`: girdi, canonical entity, birleşen kayıt, belirsiz kayıt ve karar
  sınıfı dağılımları.

Pydantic modelleri `extra="forbid"` kullanır; denetim sözleşmesine tanımsız alan
eklenemez.

## Küçük örnek

```bash
uv run python scripts/run_entity_resolution_sample.py
```

Örnek, Gün 19'daki 4 entity kaydını 13 kontrollü varyantla genişletir. Tam 25.859 chunk
işlenmez ve harici servis çağrısı yapılmaz. Denetim sonucu
`data/graph/sample_day20/audit_report.json` dosyasındadır.

Örnek kararlardan bazıları:

- `ASELSAN` + `ASELS` → `EXACT_MATCH`, `company:ASELS`.
- `Ahmet Akyol` + `Dr. Ahmet AKYOL` → aynı şirket bağlamında `EXACT_MATCH`.
- `Ahmet Akyol` + `Ahmet Akyal` → aynı raporda `HIGH_CONFIDENCE_MATCH`.
- Aynı kişi adı, ASELS ve KCHOL bağlamlarında → `DIFFERENT_ENTITY`.
- `Toplam Hasılat` + `Ciro`, aynı dönem/değer bağlamında → `EXACT_MATCH`.
- Aynı metrik ve dönem fakat farklı sayısal değer → `REVIEW_REQUIRED`, birleşme yok.
- `SİPER Ürün-1` + `SİPER Ürün-2` → model numarası çatışması nedeniyle
  `DIFFERENT_ENTITY`.

## Sürümleme

Normalizasyon sözlükleri veya eşik değerleri değiştirildiğinde `resolution_version`
artırılmalıdır. Alias ve karar kimlikleri bu sürümü içerdiğinden aynı girdi ve sürüm aynı
denetlenebilir kimlikleri üretir; farklı bir kural setinin kararları eski kayıtlarla
karışmaz.
