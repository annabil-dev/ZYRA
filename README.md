# 🚀 ZYRA CLI: Decentralized AI Agent & PoUW Network

A powerful, self-organizing decentralized AI network client and terminal-based Agentic AI framework powered by Proof-of-Useful-Work (PoUW).

## 🌟 Core Ecosystem
- **ZYRA CLI (`zyra_cmd/zyra_cli.py`):** Interactive terminal assistant with autonomous tool-calling, multi-model support, and P2P networking.
- **P2P Gossip Network (`p2p/`):** Decentralized node communication for task broadcasting and consensus.
- **Proof-of-Useful-Work (PoUW):** Consensus mechanism where AI Miner nodes execute tasks and Smart Judges validate trajectories deterministically.
- **Blockchain Integration (`blockchain/` & `mythchain/`):** EVM tokenomics (Celo/Hardhat) and sovereign Cosmos SDK L1 roadmap (MythChain).
- **AI Research (`ai/`):** Scratch-built Transformer architecture and training framework.

## 📦 Installation & Setup

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -e .
```

## 🚀 Running ZYRA CLI

```powershell
zyra
```
OR
```powershell
python -m zyra_cmd.zyra_cli
```

## Client Mode: Engine, Tasks & Result Folder

Client nodes can submit tasks without installing Ollama. The first Ollama installation
answer is remembered across CLI restarts. If you choose `n`, subsequent launches do
not repeat the installation prompt. To install/start Ollama and select a local model later:

```text
/engine
```

Set the destination for future task results before submitting:

```text
/output "D:\Hasil ZYRA"
/submit Buat aplikasi kalkulator Python
/tasks
```

On Linux/macOS, for example, use `/output ~/hasil-zyra`. Paths with spaces are supported.
`/output` with no argument shows the current folder. The default is `~/ZYRA Results`.
Each task remembers its absolute destination at submission time; changing `/output`
does not move previous or in-progress tasks.

Task IDs, progress, download status, and result locations are saved in `client.db`
under `%APPDATA%\ZYRA AI` on Windows, or `~/ZYRA AI` when `APPDATA` is unset.
When the CLI is reopened:

- A summary shows previously downloaded results and their workspace/ZIP paths.
- Pending tasks resume tracking through P2P mempool synchronization.
- Tasks completed while the client was offline are downloaded once their completion
  and result CID are received from peers.
- Failed downloads are retried while the CLI is running. Successfully saved results
  are not downloaded again, and existing result folders are not overwritten.
- `/tasks` shows the full local task history, destinations, and latest download errors.

Recovery requires a peer that still knows the task and an online node serving its
workspace. Closing the client stops local monitoring/downloads until it is reopened.
Tracking applies to tasks submitted with this version; older sessions that never
saved task history cannot be reconstructed from local history automatically.
