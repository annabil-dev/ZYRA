import React, { useState, useEffect, useRef } from 'react';
import { ethers } from 'ethers';
import './index.css';

const LandingView = ({ setView, showToast, zyraBalance }) => {
  const [displayedLines, setDisplayedLines] = useState([
    <><span className="t-prefix">ZYRA &gt;</span> <span className="t-user">Listening to network activity...</span></>
  ]);
  const [networkStats, setNetworkStats] = useState({ activeNodes: '...', mempoolSize: '0' });

  // Smooth scroll function
  const scrollToSection = (id) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch("/api/network_stats");
        if (res.ok) {
          const data = await res.json();
          setNetworkStats(data);
        }
      } catch (err) {}
    };
    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let lastKnownHash = null;
    const fetchTasks = async () => {
      try {
        const res = await fetch("/live_tasks");
        if (!res.ok) return;
        const data = await res.json();
        const tasks = data.tasks;
        
        if (tasks && tasks.length > 0) {
          const latestTask = tasks[tasks.length - 1];
          if (latestTask.hash !== lastKnownHash) {
            lastKnownHash = latestTask.hash;
            const shortWallet = latestTask.wallet.substring(0, 6) + "..." + latestTask.wallet.substring(38);
            const shortHash = latestTask.hash.substring(0, 10) + "...";
            const newLines = [
              <span className="t-dim">--- New Block Validated ---</span>,
              <><span className="t-success">✓ PoUW Task Solved by {shortWallet}</span></>,
              <><span className="t-hash">Hash: {shortHash}</span></>,
              <>💸 <span className="t-success">+{latestTask.reward} ZYRA Minted</span></>,
              <><span className="t-prefix">ZYRA &gt;</span> <span className="t-user">Listening to network activity...</span></>
            ];
            
            setDisplayedLines(prev => {
              // Keep maximum 30 lines to prevent UI lag
              const updated = [...prev, ...newLines];
              if (updated.length > 30) return updated.slice(updated.length - 30);
              return updated;
            });
          }
        }
      } catch (err) {
        // Silently fail if backend is unreachable
      }
    };

    fetchTasks();
    const interval = setInterval(fetchTasks, 3000);
    return () => clearInterval(interval);
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
          <h1>The Global Network for Decentralized AI</h1>
          <p>
            Turn your idle compute into an engine for the future. ZYRA is an open, peer-to-peer network where autonomous AI agents collaborate to solve complex tasks, secured by Proof-of-Useful-Work (PoUW) and validated by an advanced AI Smart Judge on the Celo blockchain.
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
          <h3>21M ZYRA</h3>
          <p>Maximum Supply (Hard-Capped)</p>
        </div>
        <div className="stat-card">
          <h3 style={{color: 'var(--accent-cyan)'}}>{zyraBalance > 0 ? `${zyraBalance} Mined!` : '2.1M+'}</h3>
          <p>Total ZYRA Mined (Live)</p>
        </div>
        <div className="stat-card">
          <h3>{networkStats.active_nodes || '...'}</h3>
          <p>Active Swarm Nodes (Testnet)</p>
        </div>
        <div className="stat-card">
          <h3>{networkStats.mempool_size || '0'} Tasks</h3>
          <p>Pending in Mempool</p>
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

      {/* Ecosystem / Features Section */}
      <section className="features-section" style={{paddingTop: '0'}}>
        <div className="section-header">
          <h2>What can the Swarm build?</h2>
          <p>Endless possibilities powered by zero-knowledge local inference.</p>
        </div>
        <div className="features-grid">
          <div className="feature-box">
            <div className="feature-icon" style={{color: 'var(--accent-cyan)'}}>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
            </div>
            <h4>Private Data Analysis</h4>
            <p>Analyze sensitive local datasets, financial records, or medical history without ever leaking data to centralized cloud API providers.</p>
          </div>
          <div className="feature-box">
            <div className="feature-icon" style={{color: 'var(--accent-cyan)'}}>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16c0 1.1.9 2 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/><path d="M14 3v5h5M16 13H8M16 17H8M10 9H8"/></svg>
            </div>
            <h4>Smart Contract Auditing</h4>
            <p>Deploy local AI agents to read, compile, and aggressively fuzz Web3 smart contracts to find critical zero-day vulnerabilities.</p>
          </div>
          <div className="feature-box">
            <div className="feature-icon" style={{color: 'var(--accent-cyan)'}}>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
            </div>
            <h4>Automated QA & Pipelines</h4>
            <p>Instruct the Swarm to scaffold entire end-to-end testing environments, mock data pipelines, and deployment scripts automatically.</p>
          </div>
        </div>
      </section>

      {/* Community Section */}
      <section id="community" style={{padding: '5rem 6%', textAlign: 'center', background: 'rgba(6, 182, 212, 0.03)', borderTop: '1px solid rgba(255,255,255,0.05)', borderBottom: '1px solid rgba(255,255,255,0.05)'}}>
        <h2 style={{fontSize: '2.8rem', marginBottom: '1rem'}}>Join the Global Ecosystem</h2>
        <p style={{color: 'var(--text-muted)', marginBottom: '3rem', fontSize: '1.2rem'}}>Be part of the decentralized AI revolution. Connect with developers worldwide.</p>
        
        <div style={{display: 'flex', justifyContent: 'center', gap: '2rem', flexWrap: 'wrap'}}>
          <button className="btn-outline" style={{padding: '1rem 3rem', fontSize: '1.1rem', background: '#5865F2', color: 'white', border: 'none'}}>Join Discord</button>
          <button className="btn-outline" style={{padding: '1rem 3rem', fontSize: '1.1rem', background: '#000000', color: 'white', border: '1px solid #333'}}>Follow on X</button>
          <button className="btn-outline" style={{padding: '1rem 3rem', fontSize: '1.1rem', background: '#24292e', color: 'white', border: 'none'}}>GitHub</button>
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
          <h3>ZYRA Protocol Whitepaper v2.0</h3>
          <p>Learn about our P2P Gossip Network, PoUW consensus, and the upcoming IPFS integration.</p>
          <a href="/zyra_whitepaper_v2.0.pdf" target="_blank" rel="noreferrer" className="btn-primary" style={{textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '10px', marginTop: '1rem', width: 'fit-content'}}>
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            Read Whitepaper v2.0
          </a>
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
  const [showWalletMenu, setShowWalletMenu] = useState(false);

  const getStakingInfo = (balance) => {
    const bal = parseFloat(balance);
    if (bal >= 10000) return { tier: "Tier 3 (Whale)", limit: "Unlimited tasks/hr" };
    if (bal >= 1000) return { tier: "Tier 2", limit: "100 tasks/hr" };
    if (bal >= 100) return { tier: "Tier 1", limit: "30 tasks/hr" };
    return { tier: "Tier 0", limit: "5 tasks/hr" };
  };

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
        
        // The ZyraToken contract on Celo Sepolia
        const ZYRA_CONTRACT_ADDRESS = "0x56a82386355fE89BfA2874B89e751511d65435D7";
        const erc20Abi = [
          "function balanceOf(address owner) view returns (uint256)"
        ];
        const contract = new ethers.Contract(ZYRA_CONTRACT_ADDRESS, erc20Abi, provider);
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
            <a href="#" onClick={(e) => { e.preventDefault(); setView('docs') }}>Docs</a>
          </div>
        )}
        {view !== 'landing' && (
          <div className="nav-links">
            <a href="#" onClick={(e) => { e.preventDefault(); setView('landing') }}>Home</a>
            <a href="#" onClick={(e) => { e.preventDefault(); setView('learn') }} className={view === 'learn' || view === 'whitepaper' ? 'active-link' : ''}>Learn</a>
            <a href="#" onClick={(e) => { e.preventDefault(); setView('docs') }} className={view === 'docs' ? 'active-link' : ''}>Docs</a>
          </div>
        )}
        <div style={{ position: 'relative' }}>
          <button 
            className="btn-outline" 
            onClick={walletAddress ? () => setShowWalletMenu(!showWalletMenu) : connectWallet} 
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
          
          {showWalletMenu && walletAddress && (
            <div className="wallet-dropdown" style={{
              position: 'absolute', top: '120%', right: '0', 
              background: '#0f172a', border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '8px', padding: '1.2rem', width: '280px',
              boxShadow: '0 10px 25px rgba(0,0,0,0.5)', zIndex: 100
            }}>
              <div style={{fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '0.2rem'}}>Staking Tier</div>
              <div style={{fontSize: '1.4rem', fontWeight: 'bold', color: 'var(--accent-cyan)', marginBottom: '0.2rem'}}>{getStakingInfo(zyraBalance).tier}</div>
              <div style={{fontSize: '0.9rem', color: '#fff', marginBottom: '1rem'}}>Task Limit: <span style={{fontWeight: 'bold'}}>{getStakingInfo(zyraBalance).limit}</span></div>
              
              <div style={{borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '0.8rem', marginBottom: '0.8rem'}}>
                <div style={{fontSize: '0.8rem', color: 'var(--text-muted)'}}>Connected Address</div>
                <div style={{fontSize: '0.85rem', color: '#fff', fontFamily: 'monospace', wordBreak: 'break-all'}}>{walletAddress}</div>
              </div>
              
              <button 
                className="btn-outline" 
                style={{width: '100%', padding: '0.4rem', fontSize: '0.9rem', border: '1px solid rgba(255,0,0,0.3)', color: '#ff6b6b'}}
                onClick={() => {
                  setWalletAddress('');
                  setZyraBalance('0');
                  setShowWalletMenu(false);
                  showToast("Wallet disconnected");
                }}
              >
                Disconnect
              </button>
            </div>
          )}
        </div>
      </nav>

      {/* Toast Notification */}
      <div className={`toast-notification ${toastMessage ? 'show' : ''}`}>
        <div className="toast-icon">⚠️</div>
        <div className="toast-text">{toastMessage}</div>
      </div>

      <main className="main-content">
        {view === 'landing' && <LandingView setView={setView} showToast={showToast} zyraBalance={zyraBalance} />}
        {view === 'docs' && <DocsView setView={setView} />}
        {view === 'learn' && <LearnView setView={setView} />}
        {/* Removed embedded WhitepaperView, using native PDF viewer now */}
      </main>

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
