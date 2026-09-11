# Phase 5: Pretraining System & Model Lineage

Fase 5 menetapkan fondasi *Pretraining* profesional bagi MY-AI, mengalihkan fokus dari kebenaran arsitektural (Phase 4) menuju stabilitas infrastruktur skala besar. Arsitektur Transformer Causal kini didukung oleh **ZYRA Identity System**, mekanisme toleransi kegagalan (*fault tolerance*), serta metrik terstruktur.

## ZYRA Model Identity
Semua generasi model bahasa mulai dari Phase 5 akan menyandang nama **ZYRA**.
- **Family**: `ZYRA`
- **Generation**: `ZYRA-1` (Generasi Transformer pertama dengan parameter 35–50M)
- **Variant**: `Base` (Causal LM sebelum *instruction tuning*)
- **Version**: `v0.1.0-dev`

Semua model wajib diregistrasikan ke dalam *Local Model Registry* (`ai/models/registry.py`) dengan *Model Card* (`model_card.yaml`) yang memuat silsilah pelatihannya (*Parent Model*, *Run ID*, *Tokens Seen*).

## Peningkatan Engine Pelatihan (Trainer v2.0)
Trainer di-_upgrade_ drastis untuk skenario *Pretraining*:
1. **Gradient Accumulation**: Mendukung akumulasi batch secara virtual. Memungkinkan kita melakukan pelatihan _batch_ 64 dengan VRAM seukuran *micro batch* 4, mengoptimalkan GPU *gaming* seperti RTX 4060 8GB.
2. **Scheduler (Linear Warmup + Cosine Decay)**: LR tidak lagi statis. *Warmup* menstabilkan gradien awal, dan *Cosine Decay* memperhalus pendaratan akhir untuk memeras performa.
3. **Atomic Resumption & RNG State**: Jika pelatihan dihentikan paksa (Ctrl+C), *trainer* secara atomik menyimpan `INTERRUPTED.pt` (mencakup status RNG Python, NumPy, PyTorch CPU & CUDA). Ini menjamin iterasi *resume* 100% deterministik.
4. **NaN/Inf Protection**: Otomatis menggagalkan *step* dan memberhentikan iterasi apabila *loss* atau gradien meledak.
5. **Token Accounting**: *Tokens Seen* (sejumlah N) dicatat permanen dalam _checkpoint_.

## CLI Tools
Eksekusi pelatihan tidak lagi mengandalkan _script_ coba-coba.
- `scripts/pretrain.py`: Memuat model, melakukan sinkronisasi _Dataset_, menjalankan *Trainer*, merekam `metrics.jsonl`, dan memperbarui *Model Card*.
- `scripts/benchmark_training.py`: _Dry-run throughput_ dan profiler VRAM. Membantu menentukan batas *micro batch* optimal tanpa perlu melakukan *OOM Crash* saat *Pretraining* asli.

_Stop Condition: Pengerjaan dihentikan di fase ini sebelum mengeksekusi multi-day pretraining produksi. Silakan lakukan benchmark VRAM pribadi Anda dan mulailah _training_ saat Anda siap._
