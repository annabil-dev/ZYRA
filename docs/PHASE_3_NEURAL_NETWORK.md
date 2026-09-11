# Phase 3: First Neural Network & Training Engine

Fase 3 bertujuan menguji fungsionalitas end-to-end dari _Pipeline Training_, mengonfirmasi bahwa ekosistem MY-AI (dari Dataset hingga Backpropagation dan Model Checkpointing) mampu bekerja dengan stabil sebelum kita menginjak arsitektur _Transformer_ yang lebih rumit.

## 1. Baseline Architecture (`FixedContextMLP`)
Sebagai Baseline (Sanity Model), kami menggunakan arsitektur **Multi-Layer Perceptron (MLP)** dengan konteks statis.

- **Token Embedding**: Mengubah _Token ID_ diskrit menjadi vektor _dense_.
- **Positional Embedding**: Karena MLP tidak secara _native_ memahami urutan kata (bukan _Attention_), kami menggunakan *learned embedding* sederhana untuk posisi $0$ hingga $N-1$.
- **Flattening**: Context Window $[B, T, E]$ dipipihkan menjadi $[B, T \times E]$.
- **Hidden Layers (MLP)**: Layer Linier + ReLU + Dropout yang bertujuan mentransformasikan informasi konteks statis tadi.
- **Logits**: Sebuah _Linear projection_ akhir untuk memprediksi probabilitas (Logits) token berikutnya di dalam matriks $[B, V]$.

## 2. Reusable Training Engine (`Trainer`)
`Trainer` didesain secara independen dari `FixedContextMLP`. Ia menerima abstraksi `BaseLanguageModel` yang hanya menjanjikan fungsi `forward()`.
Ini berarti _Engine_ ini:
1. Mengambil Batch (`DatasetReader`).
2. Melakukan Prediksi `logits = model(X)`.
3. Menghitung `CrossEntropyLoss`.
4. Melakukan _Backpropagation_ (`loss.backward()`) & Gradient Clipping.
5. Memperbarui Bobot via `AdamW`.
6. Melakukan evaluasi berkala tanpa mengubah bobot (`model.eval()`).

Training Engine ini **100% Siap** digunakan untuk arsitektur Transformer di Phase 4.

## 3. Checkpointing & Atomic Write
Model dapat di-jeda dan dilanjutkan kapan saja (Resume Training).
Setiap file `.pt` (PyTorch Checkpoint) menyimpan tidak hanya _Weight Matrices_, tetapi:
- Global step progress.
- Optimizer states (agar momentum AdamW tidak hilang).
- *Best Validation Loss*.
- **Fingerprint Hash** (mencegah load dataset/tokenizer yang tidak kompatibel).
- Ditulis ke `.tmp` lalu di-_rename_ agar kebal terhadap _Corrupted Saves_ akibat _Force Quit_ mendadak.

## 4. Reproducibility
Seed (`set_seed`) mengontrol _RNG_ (Random Number Generator) pada Python, NumPy, dan PyTorch sehingga inisialisasi awal bobot Neural Network selalu identik dalam eksekusi yang sama, mempermudah pelacakan *bug* dan stabilitas benchmark.

## Keterbatasan Phase 3 (Sengaja)
- Bukan Transformer, sehingga model hanya bisa menebak berdasarkan _window_ kaku, tidak memiliki _self-attention_, dan performanya pada teks nyata akan terbatas.
- Tidak ada _Instruction Tuning_ atau implementasi percakapan.
