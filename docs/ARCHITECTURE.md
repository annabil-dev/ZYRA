# Architecture Overview

Proyek ini dibangun dengan prinsip modularitas, offline-first, dan separation of concerns.

Berikut adalah diagram hubungan antar komponen:

```mermaid
flowchart TD
    A[Desktop GUI (PySide6)] --> B[Application Services]
    B --> C[AI Core (Future)]
    C --> D[PyTorch / CUDA]
    D --> E[Local Model / Data / Database]
    B --> E
```

## Desktop GUI (PySide6)
Berjalan pada thread utama (Main Thread). Menangani interaksi pengguna, menampilkan dashboard hardware, memantau training, dan chat interface. Background tasks akan di-dispatch menggunakan `QRunnable`/`QThread` (melalui `Workers`) agar UI tidak freeze.

## Application Services
Lapis tengah yang menangani:
- Configuration parsing (`configs/default.yaml`)
- Database initialization (SQLite)
- Directory / Path management
- System & Hardware detection (OS, RAM, VRAM, CUDA)
- Central Logging

## AI Core (Future)
Modul independen yang menangani:
- Tokenizer custom
- Neural Network architecture (Transformer)
- Training loops
- Inference logic
- Memory System dan RL

## PyTorch / CUDA
Berperan sebagai tensor backend dan autograd engine untuk perhitungan grafis dan matematika (tanpa menggunakan model PyTorch bawaan/pretrained).

## Local Model / Data
Semua state, history chat, logs, dataset, checkpoint, dan metadata model tersimpan secara offline di media penyimpanan lokal pengguna, tanpa ada koneksi keluar komputer.
