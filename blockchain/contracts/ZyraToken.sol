// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract ZyraToken is ERC20, Ownable {
    // 21 Million Max Supply (Bitcoin Style)
    uint256 public constant MAX_SUPPLY = 21_000_000 * 10**18;
    
    // Developer receives 10% (2.1 Million) immediately upon deployment
    uint256 public constant DEV_ALLOCATION = 2_100_000 * 10**18;
    
    // --- Security: Daily Minting Cap ---
    uint256 public constant DAILY_MINT_CAP = 100 * 10**18;
    uint256 public dailyMinted;
    uint256 public lastResetTime;

    constructor() ERC20("ZYRA AI", "ZYRA") Ownable(msg.sender) {
        // Mint 10% to the developer (deployer)
        _mint(msg.sender, DEV_ALLOCATION);
    }

    /**
     * @dev Mint tokens for Proof of Useful Work (PoUW) rewards.
     * Only the bridge server (Owner) can call this function.
     * Reverts if total supply exceeds MAX_SUPPLY.
     */
    function mintReward(address to, uint256 amount) public onlyOwner {
        require(totalSupply() + amount <= MAX_SUPPLY, "ZYRA: Max supply exceeded");
        
        // Reset daily limits if a new day has started
        if (block.timestamp >= lastResetTime + 1 days) {
            dailyMinted = 0;
            lastResetTime = block.timestamp;
        }
        
        require(dailyMinted + amount <= DAILY_MINT_CAP, "ZYRA: Daily minting cap exceeded");
        
        dailyMinted += amount;
        _mint(to, amount);
    }
}
