$ErrorActionPreference = "Stop"

$env:PYTHONPATH = (Get-Location).Path

Write-Host "--- PHASE 1: Train to step 50 ---"
..\.venv\Scripts\python scripts\pilot_train.py --config configs\default.yaml --dataset data\datasets\zyra_dataset_v0.1.0 --tokenizer mock_tokenizer_real --max-steps 50

Write-Host "--- PHASE 2: Verify & Resume to step 100 ---"
..\.venv\Scripts\python scripts\pilot_train.py --config configs\default.yaml --dataset data\datasets\zyra_dataset_v0.1.0 --tokenizer mock_tokenizer_real --max-steps 100 --verify-weights checkpoints\pilot\step_00000050.pt

Write-Host "--- PHASE 3: Interrupt Test (Stop at 105) ---"
try {
    ..\.venv\Scripts\python scripts\pilot_train.py --config configs\default.yaml --dataset data\datasets\zyra_dataset_v0.1.0 --tokenizer mock_tokenizer_real --max-steps 110 --interrupt-at 105
} catch {
    Write-Host "Caught python exit (expected due to KeyboardInterrupt)"
}

Write-Host "--- PHASE 4: Resume to Target Token Budget (Step 125) ---"
..\.venv\Scripts\python scripts\pilot_train.py --config configs\default.yaml --dataset data\datasets\zyra_dataset_v0.1.0 --tokenizer mock_tokenizer_real --max-steps 125

Write-Host "Pilot sequence completed."
