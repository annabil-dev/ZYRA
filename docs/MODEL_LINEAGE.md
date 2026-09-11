# Model Lineage

Pelacakan silsilah (Lineage) memastikan bahwa tidak ada model MY-AI yang asal-usulnya tidak diketahui.

## Format Silsilah (TrainingLineage)
Setiap `model_card.yaml` memuat segmen `training` yang menyimpan:
- **`run_id`**: ID Pelatihan (contoh: `run_20260810_214500`).
- **`total_tokens_seen`**: Jumlah token kumulatif.
- **`parent_model`**: Nama Model Generasi Induk (opsional).
- **`parent_version`**: Versi Induk (opsional).
- **`parent_checkpoint`**: Path / Hash *checkpoint* fisik tempat pelatihan ini dilanjutkan.

## Resume Training
Jika `ZYRA-1 Base v0.1.0-dev` mulai ditraining dari awal (inisialisasi acak / iterasi 0), maka `parent_checkpoint` adalah `null`.

Apabila esok harinya Anda merilis `ZYRA-1 Base v0.2.0` yang melanjutkan pelatihan (Resume) dari iterasi 5.000 `v0.1.0`, maka metadata `v0.2.0` WAJIB me-*link* kembali silsilahnya ke `v0.1.0`.

Mekanisme ini mencegah hilangnya rekam jejak dataset, waktu pelatihan, dan stabilitas turunan gradien model.
