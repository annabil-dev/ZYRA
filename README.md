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
- `/tasks` shows the full local task history, destinations, latest download errors,
  and weighted acceptance reports received from judges.

Recovery requires a peer that still knows the task and an online node serving its
workspace. Closing the client stops local monitoring/downloads until it is reopened.
Tracking applies to tasks submitted with this version; older sessions that never
saved task history cannot be reconstructed from local history automatically.

## PoUW Judge Votes (prototype, local changes after v2.1.51)

The `/judge` command signs PASS or FAIL votes using ECDSA/secp256k1. Votes bind
the task ID, trajectory hash, workspace CID, acceptance hash, verdict and reason.
Peers check the signature and judge address. Legacy tasks without weighted
criteria keep the two-distinct-address PASS/FAIL quorum. Weighted tasks sign each
Judge's per-criterion results; the canonical score uses a **2-of-3 majority per
criterion**. A 1-1 disagreement waits for the third Judge. The local miner ledger
is not final on-chain settlement.

Run two independent judge nodes for end-to-end testing. Judges need a wallet
created with `ecdsa` installed; older simulated wallets without a real 128-hex
public key cannot submit a signed vote. This is a prototype vote quorum:
judge selection and Sybil resistance are not implemented, and local SQLite
balances are not final on-chain settlement. ZIP content addressing was added in
v2.1.53; opaque IDs remain supported for older tasks.

## P2P Artifact Integrity (v2.1.53)

New automode workspace ZIP files use `sha256:<hex digest>` content IDs. Nodes
verify the seeded file and verify the complete reconstructed download against
that digest before making it available to the judge or client. Invalid chunks,
oversized chunks, and artifacts larger than 256 MiB are rejected. Legacy opaque
IDs remain readable for compatibility but carry no content-integrity guarantee.

## Weighted Acceptance Criteria

`/submit <prompt>` automatically drafts weighted acceptance criteria from the
Client prompt using the Client's local model when available. ZYRA prints the
generated rubric before registration; it is fixed into the acceptance hash before
Miner claim. If no local model is available, ZYRA creates a conservative executable
runtime rubric. To supply a carefully customized contract instead, use
`/submit --spec "acceptance.json" <prompt>`.
For multiple ZYRA nodes on one Windows account, set a distinct `ZYRA_DATA_DIR`
per process to give each node its own P2P wallet and local state. Leave Windows
`APPDATA` unchanged so Python continues to find the installed `zyra-network` package.

Each criterion has a unique lowercase `id`, client-readable `description`, positive
integer `weight`, `hard_gate`, and machine-executable `check`. Example criteria for
a `flask-web` contract:

```json
{
  "criteria": [
    {
      "id": "health-endpoint",
      "description": "Health endpoint returns HTTP 200",
      "weight": 70,
      "hard_gate": true,
      "check": {"type": "http", "path": "/health", "status": 200}
    },
    {
      "id": "status-visible",
      "description": "Dashboard shows service status",
      "weight": 30,
      "hard_gate": false,
      "check": {"type": "browser_contains", "text": "Online"}
    }
  ]
}
```

Supported check types are `application_runs`, `stdout_contains` (Python), `http`,
`browser_contains`, and `browser_fetch` (web). Judges execute the checks in the
isolated Docker runtime and attach evidence to every PASS/FAIL result. The weighted
score is the passing weight divided by total weight; a failed hard gate fails the
task regardless of score. The score is an acceptance score, not a calibrated
probability of success.

For Mythchain tasks, registration commits the weighted rubric; each Cosmos Judge
vote includes its per-criterion result JSON. The keeper recomputes the 2-of-3
criterion majority and canonical weighted score. The weighted CLI integration is
included in ZYRA v2.1.62. Mythchain validators must run the matching updated binary;
installing the Python package does not upgrade or start chain validators. Required-
chain miners use P2P for task discovery but let Mythchain decide every claim, even
when an older relay payload lacks the lease-mode marker. Reward transfers and token
settlement remain unimplemented.

## Miner/Judge Docker runtime and task dependencies

Miner task commands and independent Judge checks run in Docker; they are never
executed directly on the host. Install and start Docker Desktop/Engine, then use
`/runtime` in ZYRA to prepare the pinned Python/Flask/Chromium base image. The first
base-image build needs internet access.

Task dependencies are declared as exact `package==version` pins in the generated
`requirements.txt`. ZYRA prepares a task-specific image in a resource-limited Docker
Builder using binary wheels and a local BuildKit pip cache. Additional packages may
need internet access on their first build; repeated builds use the cache. Source
distributions, direct URLs, editable installs, and unpinned versions are rejected.
If a wheel cannot be prepared, the task reports the dependency failure instead of
pretending tests passed.

The task Runner and Judge execute with networking disabled, a read-only container
root, dropped capabilities, and CPU/memory/process limits. The Builder cache is not
mounted into the Runner. Miner preparation writes resolved wheel hashes and the
runtime fingerprint into `zyra.json`; the artifact ZIP carries this lock, and a
Judge refuses a mismatched base image, platform, runtime fingerprint, OCI image ID,
or root-filesystem fingerprint. Keep Miner and Judge on the same supported runtime
platform (`ZYRA_RUNTIME_PLATFORM`, default `linux/amd64`).

Task image tags are cached locally, with a default retention of eight; override via
`ZYRA_TASK_RUNTIME_CACHE_MAX`. BuildKit's pip cache is a separate Docker Desktop
cache and can be pruned with Docker Buildx cache-prune tools when disk space is low.
Local Ollama Planner/Coder inference remains outside this task container; this
runtime controls generated application/test dependencies and execution.

## Synthetic task catalog preview

ZYRA has an opt-in **preview-only** catalog for repeatable synthetic task ideas:

```powershell
python -m zyra_cmd.synthetic_tasks --list
python -m zyra_cmd.synthetic_tasks --seed 42 --count 3
python -m zyra_cmd.synthetic_tasks --seed 42 --category flask-web
```

The seed makes selection reproducible. Preview output includes the task prompt,
category/difficulty, executable acceptance contract, and acceptance hash. It does
not register a task, broadcast through P2P, start a Miner, or issue a reward. A
background scheduler and on-chain synthetic-task origin/budget rules are not part
of this preview command.

## Isolating multiple local nodes on one Windows account

Keep Windows `APPDATA` unchanged so the Python launcher can find the installed
package. Set `ZYRA_DATA_DIR` to a different folder for each Client/Miner/Judge
process to give each one its own local P2P wallet, ledger, and task database. Keep
the Client's data directory stable across restarts so it can recover its task
history.

```powershell
$env:APPDATA = "$env:USERPROFILE\AppData\Roaming"
$env:ZYRA_DATA_DIR = "$env:LOCALAPPDATA\ZYRA-Mythchain\miner-a"
```

## Signed Task Leases (v2.1.54+)

Miners now publish a signed 30-minute lease for a task. Peers that see competing
claims choose the same lease ID deterministically; stale leases expire back to a
retryable task, and the lease/attempt ID is bound to the submitted trajectory and
judge votes. This reduces duplicate mining and recovers tasks after a miner stops.
It is a best-effort P2P lease, not a globally atomic lock: partitions or delayed
claims can still cause duplicate work. Chain-level consensus is required for a
single globally final task owner.

Peer mempool synchronization includes signed task claims so a joining peer can
restore the active lease before considering a task. This improves convergence
when peers exchange state; it does not provide a global lock during a network
partition.

## Local MNS v0 Lookup

The interactive command `/resolve <name.myth>` looks up a small, bundled local
development registry for `.myth` names. For example, `/resolve rpc.mythchain.myth`
shows the local RPC alias. This is application-level lookup only: it does not
configure operating-system DNS, make `.myth` names resolve in browsers, or read
ownership/records from Mythchain. The default entries point to loopback and may
not represent running services. Set `ZYRA_MNS_V0_FILE` to use a different local
JSON registry file.
