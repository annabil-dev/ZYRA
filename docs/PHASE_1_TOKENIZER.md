# Phase 1: Custom Byte-Level BPE Tokenizer

Modul Tokenizer ini dibuat 100% dari awal menggunakan pendekatan **Byte-Level Byte Pair Encoding (BPE)**, terinspirasi dari arsitektur GPT-2/RoBERTa namun diimplementasikan sepenuhnya menggunakan Python (tanpa dependensi Rust/Pretrained API seperti Hugging Face).

## Alasan Byte-Level BPE
- Mampu merepresentasikan *semua* karakter Unicode tanpa harus menggunakan banyak tag `<|unk|>`.
- Input strings dikonversi ke UTF-8 bytes (0-255).
- Bytes dipetakan ke 256 karakter dasar menggunakan _ByteCodec_.
- Merge dilakukan dari tingkat byte hingga membentuk subwords yang optimal (BPE).

## Komponen
- `ByteCodec`: Mengkonversi bytes ke representasi string yang aman digabung.
- `Vocabulary`: Menyimpan peta antara token (string) ke token ID (int). Terdiri atas _special tokens_, base bytes (0-255), dan merged tokens.
- `BPE`: Fungsi matematik murni untuk mencari pasangan kemunculan terbanyak dan me-_merge_ vocabulary. Menggunakan strategi penentuan _tie_ secara deterministik.
- `TokenizerTrainer`: Looping yang memproses file `.txt` dalam _corpus_, menghitung frekuensi, dan memanggil `BPE`.
- `TokenizerSerializer`: *Save* dan *Load* ke disk (`vocab.json`, `merges.json`, `tokenizer_config.yaml`).

## Cara Penggunaan (API)
```python
from ai.tokenizer import MyAITokenizer

tokenizer = MyAITokenizer()
tokenizer.train("data/tokenizer/corpus", vocab_size=16384)

ids = tokenizer.encode("Halo dunia!")
text = tokenizer.decode(ids)

tokenizer.save("models/tokenizer/my_ai_v0001")
```

## CLI
```powershell
python scripts/train_tokenizer.py --corpus data/tokenizer/corpus --vocab-size 16384 --output models/tokenizer/v1
```
