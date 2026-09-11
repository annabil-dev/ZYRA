# Model Versioning Policy

MY-AI menerapkan kebijakan ketat dalam penamaan dan versi model.

## Nomenklatur Utama
- **Project**: MY-AI
- **Family**: ZYRA
- **Generation**: ZYRA-1
- **Variant**: Base
- **Development Version**: `v0.1.0-dev`

*(Contoh Model Identitas Lengkap: `ZYRA-1 Base v0.1.0-dev`)*

## Aturan Semantic Versioning (MAJOR.MINOR.PATCH)

### PATCH (v0.1.0 -> v0.1.1)
Digunakan untuk:
- _Bugfix_ arsitektur minor.
- Perbaikan *training pipeline*.
- Pelanjutan _checkpoint_ yang memecahkan masalah konvergensi.

### MINOR (v0.1.0 -> v0.2.0)
Digunakan untuk:
- Pembaruan set data yang signifikan.
- Peningkatan _hyperparameter_ besar (menambah _Token Budget_ secara drastis).
- Kemajuan kapabilitas tanpa merubah fundamental _Generation_.

### MAJOR (v1.0.0 -> v2.0.0)
Digunakan untuk:
- Lompatan kapabilitas raksasa.
- Mengganti format arsitektur dasar.
- Mayoritas bertepatan dengan transisi ke `ZYRA-2` (Hanya bisa dipicu oleh Persetujuan Pengguna).

## Alias Status Model
- **development**: Sedang ditraining / diuji coba.
- **candidate**: Rilis kandidat stabil.
- **stable**: Diakui tangguh untuk *Inference*.
- **best**: *Checkpoint* terbaik di generasinya.

_Semua perubahan versi akan tercatat di dalam `model_card.yaml` masing-masing *checkpoint*._
