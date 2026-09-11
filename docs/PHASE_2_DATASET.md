# Phase 2: Memory-Mapped Dataset Pipeline

Dataset Pipeline di MY-AI difokuskan untuk mengonversi raw teks (Corpus) menjadi _array_ biner yang dapat diload seketika ke memori (lazy load) menggunakan `numpy.memmap`. Ini mencegah *Out Of Memory (OOM)* meskipun memproses ber-Gigabyte data.

## Spesifikasi Data
- **Format**: `.bin` (Numpy Binary), tersusun atas 1D _array_ dari token IDs.
- **Tipe Data (dtype)**: Dinamis (bisa `uint16` jika vocab $\leq$ 65535, atau `uint32` jika vocab sangat besar). Saat ini (Phase 1) vocab dibatasi 16384, maka digunakan `uint16`.
- **Indeks**: File `.idx` menyimpan metadata per-dokumen (seperti posisi start token, jumlah token, dan asal referensi dokumen).

## Fitur Utama
1. **Document Boundaries**: Pemisahan antar dokumen selalu ditandai dengan _special token_ `<|eos|>`. Splitting (Train/Val/Test) terjadi **sebelum** token digabung, untuk mencegah bocornya separuh konteks dokumen ke set validasi.
2. **Tokenizer Fingerprinting**: Hash berbasis konfigurasi vocab dan merges untuk mencegah dataset diload menggunakan versi tokenizer yang salah (ini akan membangkitkan `ValueError` ketat).
3. **Atomic Finalization**: Selama _build_, tokenizer menulis ke ekstensi `.tmp.bin`. Jika gagal di tengah jalan, `.tmp.bin` tidak akan diubah namanya menjadi versi final, sehingga pipeline kebal korupsi data putus di tengah jalan.
4. **Sequence Sampling (Causal LM)**: `DatasetReader` bisa di-query `reader.get_batch(split="train", batch_size=4, context_length=256)`. Ini secara otomatis mengambil bongkahan token sepanjang $N+1$ dan membaginya menjadi `X` (Input) dan `Y` (Target).

## Komponen
- `ai.dataset.builder.DatasetBuilder`: Konverter Corpus -> Bin.
- `ai.dataset.reader.DatasetReader`: Memmap Loader & Sampler.
- `ai.dataset.document.DocumentReader`: Corpus scanner & Splitter.
- `ai.dataset.metadata.DatasetMetadata`: Hash generator & Validator.

## Contoh Penggunaan
```python
from ai.tokenizer import MyAITokenizer
from ai.dataset import DatasetBuilder, DatasetReader

# Inisialisasi
tokenizer = MyAITokenizer.load("models/tokenizer/v1")
builder = DatasetBuilder(tokenizer, config={"split_ratio": ...}, logger=logger)

# Build
builder.build("data/tokenizer/corpus", "data/datasets/v1")

# Baca dan sampel
reader = DatasetReader("data/datasets/v1", tokenizer)
X, Y = reader.get_batch("train", batch_size=8, context_length=512)
```
