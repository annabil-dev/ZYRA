// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract ZyraToken is ERC20, Ownable {
    // 100 Million Max Supply
    uint256 public constant MAX_SUPPLY = 100_000_000 * 10**18;
    
    // Developer receives 10% (10 Million) immediately upon deployment
    uint256 public constant DEV_ALLOCATION = 10_000_000 * 10**18;

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
        _mint(to, amount);
    }
}
