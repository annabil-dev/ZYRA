import React, { useState, useEffect, useRef } from 'react';
import { ethers } from 'ethers';
import './index.css';

const LandingView = ({ setView, showToast }) => {
  const [displayedLines, setDisplayedLines] = useState([]);
  
  // Smooth scroll function
  const scrollToSection = (id) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  useEffect(() => {
    const sequence = [
      { delay: 800, text: <><span className="t-prefix">ZYRA &gt;</span> <span className="t-user">/automode "Train a neural network model"</span></> },
      { delay: 1500, text: <span className="t-dim">Initializing Swarm Intelligence...</span> },
      { delay: 2000, text: <>✓ <span className="t-success">Planner Agent deployed</span></> },
      { delay: 2500, text: <>✓ <span className="t-success">Coder Agent deployed</span></> },
      { delay: 4000, text: <span className="t-dim">Writing neural_net.py (245 lines)...</span> },
      { delay: 5000, text: <span className="t-dim">Executing script...</span> },
      { delay: 6500, text: <>✓ <span className="t-success">Execution complete. Accuracy: 96.8%</span></> },
      { delay: 7500, text: <span className="t-dim">Generating Trajectory Hash...</span> },
      { delay: 8000, text: <span className="t-hash">0x8f2a...9c4e</span> },
      { delay: 9000, text: <span className="t-dim">Submitting Proof of Useful Work to Celo...</span> },
      { delay: 10500, text: <>✓ <span className="t-success">Consensus reached. Block confirmed.</span></> },
      { delay: 11500, text: <span className="t-dim">Minting ZYRA Token Reward...</span> },
      { delay: 12500, text: <>💸 <span className="t-success">+2.5 ZYRA transferred to wallet 0x4aB...9f1A</span></> },
      { delay: 13500, text: <><span className="t-prefix">ZYRA &gt;</span> <span className="t-user">Task finished successfully.</span></> },
    ];

    const timeouts = sequence.map((item, index) => 
      setTimeout(() => {
        setDisplayedLines(prev => [...prev, item.text]);
      }, item.delay)
    );

    return () => timeouts.forEach(clearTimeout);
  }, []);

  // Auto-scroll to bottom
  const terminalRef = useRef(null);
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [displayedLines]);

  return (
    <>
      <section className="hero">
        <div className="hero-content">
          <h1>Decentralized<br/>Agentic Swarm</h1>
          <p>
            ZYRA is a next-generation protocol where autonomous AI agents collaborate to solve complex computing tasks, 
            secured by Proof-of-Useful-Work (PoUW) on the Celo network.
          </p>
          <div className="hero-actions">
            <button className="btn-primary" onClick={() => scrollToSection('ecosystem')} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              Explore the Protocol 
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"></line>
                <polyline points="12 5 19 12 12 19"></polyline>
              </svg>
            </button>
            <button className="btn-outline" onClick={() => scrollToSection('network')}>Live Stats</button>
          </div>
        </div>

        <div className="terminal-container">
          <div className="terminal-header">
            <div className="dot red"></div>
            <div className="dot yellow"></div>
            <div className="dot green"></div>
            <span className="terminal-title">Terminal - ZYRA Node</span>
            <div style={{width: '40px'}}></div> {/* Spacer for balance */}
          </div>
          <div className="terminal-body" style={{overflowY: 'auto', scrollBehavior: 'smooth'}} ref={terminalRef}>
            {displayedLines.map((line, index) => (
              <div key={index} className="t-line">
                {line}
              </div>
            ))}
            
            <div className="t-line" style={{ marginTop: 'auto' }}>
              <span className="t-prefix">ZYRA &gt;</span>
              <span><span className="cursor"></span></span>
            </div>
          </div>
        </div>
      </section>

      {/* Network Stats Section */}
      <section id="network" className="stats-section">
        <div className="stat-card">
          <h3>4,102</h3>
          <p>Active Swarm Nodes</p>
        </div>
        <div className="stat-card">
          <h3>1.2M+</h3>
          <p>Tasks Solved</p>
        </div>
        <div className="stat-card">
          <h3>~2.5s</h3>
          <p>Avg Consensus Time</p>
        </div>
        <div className="stat-card">
          <h3>21M ZYRA</h3>
          <p>Maximum Supply</p>
        </div>
      </section>

      {/* Ecosystem / Features Section */}
      <section id="ecosystem" className="features-section">
        <div className="section-header">
          <h2>How ZYRA Works</h2>
          <p>A seamless bridge between Agentic AI and Web3.</p>
        </div>
        
        <div className="workflow-container">
          <div className="workflow-line"></div>
          
          <div className="workflow-step">
            <div className="workflow-icon-box">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            </div>
            <h4>1. User Prompt</h4>
            <p>Submit a complex coding or data task via the CLI.</p>
          </div>

          <div className="workflow-step">
            <div className="workflow-icon-box">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path><path d="M16.2 7.8l-2 2"></path><path d="M7.8 7.8l2 2"></path></svg>
            </div>
            <h4>2. Swarm Execution</h4>
            <p>Planner and Coder agents autonomously write, test, and execute the solution.</p>
          </div>

          <div className="workflow-step">
            <div className="workflow-icon-box">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
            </div>
            <h4>3. PoUW Verification</h4>
            <p>Trajectory hashes are cryptographically verified on the Celo network.</p>
          </div>

          <div className="workflow-step">
            <div className="workflow-icon-box">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
            </div>
            <h4>4. Token Reward</h4>
            <p>Earn newly minted ZYRA tokens directly to your wallet for providing useful compute.</p>
          </div>
        </div>
      </section>

      {/* Core Advantages Section */}
      <section className="features-section" style={{paddingTop: '0'}}>
        <div className="section-header">
          <h2>Why Run a ZYRA Node?</h2>
          <p>Unmatched privacy, true decentralization, and real rewards.</p>
        </div>
        <div className="features-grid">
          <div className="feature-box">
            <div className="feature-icon" style={{color: 'var(--accent-cyan)'}}>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
            </div>
            <h4>100% Local Execution</h4>
            <p>Your data never leaves your machine. ZYRA runs AI models entirely on your local hardware, ensuring absolute privacy and zero reliance on expensive API providers.</p>
          </div>
          <div className="feature-box">
            <div className="feature-icon" style={{color: 'var(--accent-cyan)'}}>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
            </div>
            <h4>Open Decentralization</h4>
            <p>Anyone with a computer can become a node. No gatekeepers, no centralized servers. Just raw community-driven compute power.</p>
          </div>
          <div className="feature-box">
            <div className="feature-icon" style={{color: 'var(--accent-cyan)'}}>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>
            </div>
            <h4>Earn While Sleeping</h4>
            <p>Turn idle compute into an asset. Leave your ZYRA node running overnight to solve network tasks and mine tokens effortlessly.</p>
          </div>
        </div>
      </section>

      <section id="developers" style={{padding: '5rem 6%', textAlign: 'center'}}>
        <h2 style={{fontSize: '2.5rem', marginBottom: '1rem'}}>Ready to Build?</h2>
        <p style={{color: 'var(--text-muted)', marginBottom: '2rem'}}>Join the testnet and start running your own ZYRA node today.</p>
        <button className="btn-primary" onClick={() => setView('docs')}>View Documentation</button>
      </section>
    </>
  );
};

const DocsView = ({ setView }) => {
  const [activeStep, setActiveStep] = useState('install');
  const [displayedLines, setDisplayedLines] = useState([]);
  const terminalRef = useRef(null);

  const steps = {
    install: {
      title: "1. Installation",
      content: "Install ZYRA globally using pip. We highly recommend using a virtual environment (venv) to prevent dependency conflicts.",
      code: "pip install zyra-network",
      terminalSequence: [
        { delay: 500, text: <><span className="t-prefix">~$</span> <span className="t-user">pip install zyra-network</span></> },
        { delay: 1500, text: <span className="t-dim">Collecting zyra-network...</span> },
        { delay: 2500, text: <span className="t-dim">Downloading zyra_network-1.1.12-py3-none-any.whl</span> },
        { delay: 3500, text: <>✓ <span className="t-success">Successfully installed zyra-network-1.1.12</span></> }
      ]
    },
    config: {
      title: "2. Configuration",
      content: "Initialize your ZYRA node by selecting your local LLM and providing a Celo EVM Wallet address to receive PoUW rewards.",
      code: "zyra config",
      terminalSequence: [
        { delay: 500, text: <><span className="t-prefix">~$</span> <span className="t-user">zyra config</span></> },
        { delay: 1200, text: <><span className="t-dim">Select Local Planner Model:</span> <span className="t-hash">llama3.1:8b</span></> },
        { delay: 2200, text: <><span className="t-dim">Enter EVM Wallet Address:</span> <span className="t-hash">0x4aB...9f1A</span></> },
        { delay: 3000, text: <>✓ <span className="t-success">Configuration securely saved to .env</span></> }
      ]
    },
    run: {
      title: "3. Run the Swarm",
      content: "Use the automode flag to delegate a complex task to the autonomous Planner and Coder agents.",
      code: "zyra\n> /automode \"Build a python snake game\"",
      terminalSequence: [
        { delay: 500, text: <><span className="t-prefix">ZYRA &gt;</span> <span className="t-user">/automode "Build a python snake game"</span></> },
        { delay: 1500, text: <span className="t-dim">Delegating to Planner Agent...</span> },
        { delay: 2500, text: <span className="t-dim">Coder Agent writing snake_game.py...</span> },
        { delay: 4000, text: <>✓ <span className="t-success">Task completed autonomously.</span></> }
      ]
    }
  };

  useEffect(() => {
    setDisplayedLines([]);
    const sequence = steps[activeStep].terminalSequence;
    
    const timeouts = sequence.map((item) => 
      setTimeout(() => {
        setDisplayedLines(prev => [...prev, item.text]);
      }, item.delay)
    );

    return () => timeouts.forEach(clearTimeout);
  }, [activeStep]);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [displayedLines]);

  return (
    <div className="docs-container">
      <div className="docs-sidebar">
        <h3>Documentation</h3>
        <ul>
          <li className={activeStep === 'install' ? 'active' : ''} onClick={() => setActiveStep('install')}>Installation</li>
          <li className={activeStep === 'config' ? 'active' : ''} onClick={() => setActiveStep('config')}>Configuration</li>
          <li className={activeStep === 'run' ? 'active' : ''} onClick={() => setActiveStep('run')}>Run the Swarm</li>
        </ul>
        
        <button className="btn-outline" onClick={() => setView('landing')} style={{marginTop: 'auto', width: '100%', fontSize: '0.9rem', padding: '0.5rem'}}>
          &larr; Back to Home
        </button>
      </div>
      
      <div className="docs-main">
        <div className="docs-content">
          <h2 style={{fontSize: '2.5rem', marginBottom: '1.5rem'}}>{steps[activeStep].title}</h2>
          <p style={{fontSize: '1.2rem', color: 'var(--text-muted)', marginBottom: '2rem', lineHeight: '1.6'}}>
            {steps[activeStep].content}
          </p>
          
          <div className="code-block" style={{background: 'rgba(0,0,0,0.4)', padding: '1.5rem', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)', marginBottom: '2rem'}}>
            <pre style={{color: 'var(--accent-cyan)', fontFamily: '"JetBrains Mono", monospace'}}>{steps[activeStep].code}</pre>
          </div>
        </div>

        <div className="docs-terminal">
          <div className="terminal-container" style={{transform: 'none', height: '400px'}}>
            <div className="terminal-header">
              <div className="dot red"></div>
              <div className="dot yellow"></div>
              <div className="dot green"></div>
              <span className="terminal-title">Interactive CLI</span>
            </div>
            <div className="terminal-body" style={{overflowY: 'auto', scrollBehavior: 'smooth'}} ref={terminalRef}>
              {displayedLines.map((line, index) => (
                <div key={index} className="t-line">
                  {line}
                </div>
              ))}
              <div className="t-line" style={{ marginTop: 'auto' }}>
                <span className="cursor"></span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const LearnView = ({ setView }) => {
  return (
    <div className="learn-container">
      <div className="learn-header">
        <h1>Learn ZYRA</h1>
        <p>Your guide to the future of decentralized Agentic AI and Proof of Useful Work.</p>
      </div>

      <div className="learn-grid">
        <div className="learn-card">
          <div className="learn-icon" style={{color: '#3b82f6'}}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
          </div>
          <h3>What is Local Agentic AI?</h3>
          <p>Traditional AI relies on centralized clouds like OpenAI. ZYRA empowers you to run autonomous agent swarms entirely on your local hardware (via Ollama or DeepSeek), ensuring zero API costs and absolute data privacy.</p>
        </div>

        <div className="learn-card">
          <div className="learn-icon" style={{color: '#8b5cf6'}}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
          </div>
          <h3>Proof of Useful Work (PoUW)</h3>
          <p>Unlike Bitcoin which wastes electricity on pointless math, ZYRA nodes secure the network by solving real-world AI tasks. Your AI's execution trajectory is hashed and validated on the Celo blockchain.</p>
        </div>

        <div className="learn-card">
          <div className="learn-icon" style={{color: '#10b981'}}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
          </div>
          <h3>ZYRA Tokenomics</h3>
          <p>The ZYRA economy is strictly capped at 21,000,000 tokens. Tokens are minted as rewards for miners who successfully execute tasks and provide consensus for the network.</p>
        </div>
      </div>

      <div className="whitepaper-cta">
        <div className="whitepaper-content">
          <h2>Read the Official Whitepaper</h2>
          <p>Dive deep into the mathematical models, cryptographic validation, and the architecture of the ZYRA Swarm.</p>
          <button className="btn-primary" onClick={() => setView('whitepaper')}>Read Whitepaper v1.0</button>
        </div>
        <div className="whitepaper-image">
          <svg width="120" height="120" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" strokeWidth="1" opacity="0.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
        </div>
      </div>
    </div>
  );
};

const WhitepaperView = ({ setView }) => {
  return (
    <div className="whitepaper-container">
      <button className="btn-outline" onClick={() => setView('learn')} style={{marginBottom: '2rem'}}>
        &larr; Back to Learn
      </button>
      <div className="whitepaper-doc">
        <h1 style={{fontSize: '2.8rem', textAlign: 'center', marginBottom: '1.5rem'}}>ZYRA: A Peer-to-Peer Decentralized Agentic Swarm & Proof of Useful Work</h1>
        
        <div className="wp-author" style={{textAlign: 'center', marginBottom: '3rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '2rem'}}>
          <p style={{fontSize: '1.3rem', fontWeight: 'bold', color: '#0f172a', margin: '0 0 0.5rem 0'}}>Annabil Hisyam Muyassar</p>
          <p style={{margin: '0 0 1rem 0'}}><a href="mailto:anabilhisyam23@gmail.com" style={{color: '#3b82f6', textDecoration: 'none'}}>anabilhisyam23@gmail.com</a></p>
          <p style={{fontSize: '0.9rem', color: '#64748b', margin: '0'}}>ZYRATechnology | Draft v1.0 | September 2026</p>
        </div>
        
        <h2>1. Introduction</h2>
        <p>The contemporary landscape of Artificial Intelligence is predominantly governed by centralized cloud entities. This oligopoly inherently introduces critical vulnerabilities, including opaque data handling, exorbitant API pricing structures, and systemic single points of failure. Concurrently, traditional blockchain consensus mechanisms, notably Proof of Work (PoW) pioneered by Bitcoin, require vast expenditures of electrical energy to compute arbitrary cryptographic hashes—a process devoid of intrinsic societal utility.</p>
        <p>ZYRA proposes a novel paradigm that bridges the computational prowess of Local Agentic AI with the cryptographic immutability of Web3. By leveraging localized Large Language Models (LLMs), ZYRA establishes an autonomous peer-to-peer network capable of executing complex generative and analytical tasks. The integrity of these executions is mathematically verifiable on the Celo blockchain via a consensus algorithm defined herein as <strong>Proof of Useful Work (PoUW)</strong>.</p>
        
        <h2>2. Network Architecture: The Autonomous Swarm</h2>
        <p>The fundamental unit of the ZYRA network is a Node. Each node encapsulates an autonomous Swarm Architecture composed of specialized, locally instantiated AI agents:</p>
        <ul>
          <li><strong>The Planner Agent:</strong> Responsible for semantic parsing of user prompts, task atomization, and chronological delegation. It operates via quantized inference models (e.g., Llama 3) to ensure deterministic reasoning.</li>
          <li><strong>The Coder Agent:</strong> An execution-focused sub-agent that translates atomic tasks into programmatic actions, interacts securely with the local file system, and validates syntax before output generation.</li>
        </ul>
        <p>By enforcing 100% local inference, the ZYRA node guarantees absolute zero data leakage, effectively neutralizing the privacy risks associated with centralized API transmissions.</p>

        <h2>3. Proof of Useful Work (PoUW) Mechanics</h2>
        <p>In the ZYRA protocol, computational effort is exclusively directed toward solving tangible AI tasks. The verification of this work relies on deterministic state transitions.</p>
        <p>When a ZYRA node completes a delegated task (e.g., generating a neural network script or establishing a data pipeline), the network captures the full state transition matrix, including the Abstract Syntax Tree (AST) of the generated code and the terminal <code>stdout</code> logs. This contiguous data structure is defined as the <em>Execution Trajectory</em>.</p>
        <p>The Trajectory undergoes a cryptographic hash function (SHA-256):</p>
        <p style={{background: '#f1f5f9', padding: '1rem', borderRadius: '8px', fontFamily: 'monospace', fontSize: '0.95rem', overflowX: 'auto'}}>H(T) = SHA-256( Prompt_Hash || State_Delta || Timestamp || Node_PubKey )</p>
        <p>This output <code>H(T)</code> is submitted as a cryptographic payload to the ZYRA Smart Contract residing on the Celo blockchain. A decentralized network of validator nodes probabilistically simulates the Trajectory (or, in v2.0, utilizes zk-SNARKs for constant-time verification) to achieve consensus. Upon cryptographic validation, the block is confirmed.</p>
        
        <h2>4. Celo EVM Integration</h2>
        <p>ZYRA strategically deploys its consensus layer on the Celo network. As an Ethereum Virtual Machine (EVM) compatible Layer 1 blockchain, Celo provides block finality in ~5 seconds and operates on a carbon-negative Proof of Stake (PoS) consensus. This synergy ensures that ZYRA's PoUW validation transactions are executed with near-zero latency and negligible gas fees, maximizing the economic yield for node operators.</p>

        <h2>5. Economic Model & Tokenomics</h2>
        <p>The ZYRA token ($ZYRA) is the native economic utility asset of the ecosystem. It adopts a strictly deflationary, hard-capped macroeconomic model:</p>
        <ul>
          <li><strong>Maximum Supply:</strong> 21,000,000 ZYRA (Algorithmic hard-cap, non-inflatable).</li>
          <li><strong>Block Reward Issuance:</strong> Minted dynamically via the Smart Contract. The issuance rate is inversely proportional to the total network hash rate and the computational complexity of the validated PoUW tasks.</li>
          <li><strong>Halving Schedule:</strong> Block rewards decay geometrically every 2,100,000 validated tasks, mimicking Bitcoin's digital scarcity architecture.</li>
          <li><strong>Slashing Mechanism:</strong> Nodes that submit malicious or falsified Trajectory hashes are penalized via the slashing of their staked ZYRA collateral.</li>
        </ul>
        
        <h2>6. Conclusion</h2>
        <p>ZYRA redefines the intersection of AI and blockchain by transforming idle compute into a cryptographically secured, globally accessible supercomputer. By replacing the arbitrary energy waste of PoW with the intrinsic utility of PoUW, ZYRA establishes an equitable, privacy-first, and economically sustainable ecosystem for the future of decentralized Artificial Intelligence.</p>
        
        <div className="wp-footer">
          <p>&copy; 2026 ZYRATechnology. All rights reserved.</p>
        </div>
      </div>
    </div>
  );
};

function App() {
  const [view, setView] = useState('landing');
  const [toastMessage, setToastMessage] = useState('');
  const [walletAddress, setWalletAddress] = useState('');
  const [zyraBalance, setZyraBalance] = useState('0');

  const showToast = (message) => {
    setToastMessage(message);
    setTimeout(() => {
      setToastMessage('');
    }, 3000);
  };

  const connectWallet = async () => {
    if (typeof window.ethereum !== 'undefined') {
      try {
        const provider = new ethers.BrowserProvider(window.ethereum);
        const accounts = await provider.send("eth_requestAccounts", []);
        const address = accounts[0];
        
        // Ensure Celo Sepolia (Chain ID 11142220)
        const network = await provider.getNetwork();
        if (network.chainId !== 11142220n) {
            showToast("Please switch MetaMask to Celo Sepolia Testnet.");
            return;
        }
        
        setWalletAddress(address);
        
        // Fetch ZYRA Balance
        const contractAddress = "0x82d27D40463a1213e4209201613A2fA144Dc94b7";
        const erc20Abi = [
          "function balanceOf(address owner) view returns (uint256)"
        ];
        const contract = new ethers.Contract(contractAddress, erc20Abi, provider);
        const balance = await contract.balanceOf(address);
        setZyraBalance(parseFloat(ethers.formatEther(balance)).toFixed(1));
        
        showToast("Wallet connected securely to Celo Network!");
      } catch (error) {
        showToast("Failed to connect wallet.");
        console.error(error);
      }
    } else {
      showToast("Please install MetaMask to connect.");
    }
  };

  return (
    <>
      {/* Background Network Nodes */}
      <div className="network-node" style={{top: '20%', left: '15%'}}></div>
      <div className="network-node" style={{top: '60%', left: '10%'}}></div>
      <div className="network-node" style={{top: '30%', left: '85%'}}></div>
      <div className="network-node" style={{top: '75%', left: '80%'}}></div>
      <div className="network-node" style={{top: '85%', left: '30%'}}></div>
      <div className="network-node" style={{top: '15%', left: '60%'}}></div>

      <nav className="navbar">
        <div className="logo" style={{cursor: 'pointer'}} onClick={() => setView('landing')}>
          <img 
            src="/zyra_logo_transparent.png" 
            alt="ZYRA Logo" 
            className="logo-icon"
            style={{ 
              width: '64px', 
              height: '64px', 
              objectFit: 'contain',
              marginRight: '-4px'
            }} 
          />
          <span>ZYRA</span>
        </div>
        {view === 'landing' && (
          <div className="nav-links">
            <a href="#ecosystem" onClick={(e) => { e.preventDefault(); document.getElementById('ecosystem')?.scrollIntoView({behavior: 'smooth'}) }}>Ecosystem</a>
            <a href="#network" onClick={(e) => { e.preventDefault(); document.getElementById('network')?.scrollIntoView({behavior: 'smooth'}) }}>Network</a>
            <a href="#developers" onClick={(e) => { e.preventDefault(); document.getElementById('developers')?.scrollIntoView({behavior: 'smooth'}) }}>Developers</a>
            <a href="#" onClick={(e) => { e.preventDefault(); setView('learn') }}>Learn</a>
          </div>
        )}
        {view !== 'landing' && (
          <div className="nav-links">
            <a href="#" onClick={(e) => { e.preventDefault(); setView('landing') }}>Home</a>
            <a href="#" onClick={(e) => { e.preventDefault(); setView('learn') }} className={view === 'learn' || view === 'whitepaper' ? 'active-link' : ''}>Learn</a>
            <a href="#" onClick={(e) => { e.preventDefault(); setView('docs') }} className={view === 'docs' ? 'active-link' : ''}>Docs</a>
          </div>
        )}
        <button 
          className="btn-outline" 
          onClick={walletAddress ? () => showToast(`Connected: ${walletAddress}`) : connectWallet} 
          style={{ padding: '0.5rem 1.2rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          {walletAddress ? (
            <>
               <span style={{color: 'var(--accent-cyan)'}}>{zyraBalance} ZYRA</span>
               <span style={{opacity: 0.5}}>|</span>
               <span>{walletAddress.substring(0, 6)}...{walletAddress.substring(38)}</span>
            </>
          ) : (
            'Connect Wallet'
          )}
        </button>
      </nav>

      {/* Toast Notification */}
      <div className={`toast-notification ${toastMessage ? 'show' : ''}`}>
        <div className="toast-icon">⚠️</div>
        <div className="toast-text">{toastMessage}</div>
      </div>

      {view === 'landing' && <LandingView setView={setView} showToast={showToast} />}
      {view === 'docs' && <DocsView setView={setView} />}
      {view === 'learn' && <LearnView setView={setView} />}
      {view === 'whitepaper' && <WhitepaperView setView={setView} />}

      <footer className="footer">
        <div className="socials">
          <svg className="social-icon" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
          </svg>
          <svg className="social-icon" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 4s-.7 2.1-2 3.4c1.6 10-9.4 17.3-18 11.6 2.2.1 4.4-.6 6-2C3 15.5.5 9.6 3 5c2.2 2.6 5.6 4.1 9 4-.9-4.2 4-6.6 7-3.8 1.1 0 3-1.2 3-1.2z"></path>
          </svg>
          <svg className="social-icon" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
            <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
            <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
          </svg>
        </div>
        <div>
          &copy; {new Date().getFullYear()} ZYRATechnology. All rights reserved.
        </div>
      </footer>
    </>
  );
}

export default App;
