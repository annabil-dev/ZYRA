# Phase 0: Windows Desktop Foundation

Pada Phase 0, fokus utama adalah menetapkan fondasi software engineering (desktop application base) tanpa implementasi komponen AI apa pun.

## Capaian Phase 0:
1. **Struktur Proyek Modular**: `app`, `core`, `ui`, `ai`, `data`, `tests`, dll terinisialisasi.
2. **Manajemen Konfigurasi YAML**: Dapat membaca dan melakukan override.
3. **Deteksi Hardware Aman**: PyTorch digunakan untuk mengecek ketersediaan GPU NVIDIA dan VRAM tanpa crash pada sistem yang tidak mendukung (fallbacks implemented).
4. **Desktop GUI (PySide6)**: Tampilan native Windows, dengan Sidebar Menu modern, Dashboard (menampilkan status PC/GPU), Logs Page (menampilkan log aplikasi secara real time), serta dummy pages untuk modul AI selanjutnya.
5. **Worker Threads Base**: Siap digunakan untuk proses berat tanpa UI freeze.
6. **Local Database & Offline Design**: Tidak ada request eksternal; state tersimpan di SQLite lokal.
7. **Pengujian (Tests)**: Suite dasar untuk modul core telah disiapkan.

Phase ini meletakkan batu loncatan yang kuat agar pengembangan _neural network_ di fase-fase berikutnya dapat berjalan di dalam ekosistem aplikasi yang stabil, tidak mudah freeze, dan informatif bagi penggunanya.
