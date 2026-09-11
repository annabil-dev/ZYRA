# MY-AI

A locally built, trained, and executed Artificial Intelligence desktop application for Windows.

## Tujuan Project
Proyek ini dibuat untuk membangun neural network Transformer dan seluruh sistem pendukung AI dari awal tanpa bergantung pada layanan cloud, API eksternal, atau model pre-trained yang sudah ada (seperti OpenAI, Claude, Llama, dll). 
Tujuan akhirnya adalah memiliki AI Assistant pribadi yang berjalan sepenuhnya lokal di komputer pengguna.

## Requirements
- Windows 64-bit
- Python 3.10+
- Hardware minimal: CPU + RAM (Rekomendasi: NVIDIA GPU dengan CUDA support)

## Setup Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\activate
```

## Install Dependencies
Project ini menggunakan `pyproject.toml` untuk manajemen dependensi minimal.
```powershell
pip install -e .[dev]
```
Dependensi utama:
- PySide6 (Desktop GUI)
- PyYAML (Configuration)
- PyTorch (Hardware detection, Tensor/Autograd)

## Menjalankan Aplikasi
```powershell
python run.py
```

## Menjalankan Test
```powershell
pytest tests/
```
