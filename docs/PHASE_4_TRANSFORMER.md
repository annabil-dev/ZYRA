# Phase 4: Decoder-Only Transformer (Brain v0.1)

Fase 4 memperkenalkan arsitektur puncak MY-AI: **Causal Decoder-Only Transformer**, sebuah model bahasa moderen yang mengimplementasikan struktur mandiri murni tanpa meminjam *pre-trained model* (seperti HF Transformers).

## Arsitektur MY-AI Brain v0.1
Model `MyAIDecoderTransformer` mengandalkan komponen-komponen unggulan berikut:

1. **Rotary Positional Embedding (RoPE)**: Informasi posisional ditambahkan dengan memutar (merotasi) fitur Query dan Key berdasarkan posisi _sequence_. MY-AI telah menerapkan **RoPE Caching** melalui `.register_buffer()`, mempercepat eksekusi CUDA sekaligus menghemat VRAM dengan membatasi regenerasi rotasi.
2. **RMSNorm (Root Mean Square Normalization)**: Digunakan dalam arsitektur **Pre-Norm** pada semua iterasi matriks residual blok. Ia lebih stabil dan efisien dibandingkan *LayerNorm* biasa karena mengesampingkan komponen _mean centering_.
3. **Multi-Head Causal Self-Attention**: Ekstraksi konteks dilakukan pada proyeksi *Query, Key, Value* independen, dibagi ke sejumlah _heads_, dipasangkan dengan **Causal Mask** (Segitiga Atas `-inf`) absolut. Kami memiliki _Automated Test_ ketat untuk memastikan tidak ada informasi "masa depan" yang bocor ke token "masa lalu" selama inferensi dan komputasi _loss_.
4. **SwiGLU Feed-Forward Network**: Menyuntikkan _non-linearity_ menggunakan `SiLU(Gate) * Up`, mengungguli FFN relu standar dengan jumlah parameter yang setara secara dimensi.
5. **Weight Tying**: _Token Embedding_ (input) dan _LM Head_ (output projection) dipaksa membagi memori bobot (parameter) yang sama di CUDA/CPU untuk efisiensi ruang parameter, diatur via config `tie_word_embeddings: true`.

## Flow Tensor (Dimensionalitas)
- **Input_IDs**: `[B, T]`
- **Embeddings**: `[B, T, D]`
- **MHA Projection (Q,K,V)**: `[B, H, T, HeadDim]`
- **RoPE Application**: Hanya dimodulasikan di Q dan K.
- **Logits Output**: `[B, T, V]`

## Training Pipeline
_DatasetReader_ MY-AI menyajikan sampel berisi $N+1$ sekuens. `Trainer` secara cerdas mengisolasi variabel Input (`X = seq[:, :-1]`) dan Target (`Y = seq[:, 1:]`). Logits 3D akan dipipihkan sebelum disalurkan ke komputasi *Cross Entropy Loss*, menjamin pembaruan turunan komprehensif bagi sekitar 35.6 juta parameternya.

## Profil Model Target
- **Brain v0.1 Default**: _8 Layers, 512 Hidden Size, 8 Heads, 256 Context Length._ Mengincar ukuran ~35 Juta parameter (bergantung final _vocab size_ dari Tokenizer lokal Anda).
- **Development & Tiny**: Profile ringkas yang dimuat saat menjalankan `pytest` di lingkungan CI lokal Anda agar uji validasi arsitektur tidak meledakkan memori lokal.
