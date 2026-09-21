const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  const tokenAddress = "0x56a82386355fE89BfA2874B89e751511d65435D7";
  const userAddress = "0xB7ddC49E7Ad32a5D18D9fC90F789b366Fc2Ff334";
  
  const token = await hre.ethers.getContractAt("ZyraToken", tokenAddress);
  
  console.log("Minting 99 ZYRA to", userAddress, "as migration bonus...");
  const tx = await token.mintReward(userAddress, hre.ethers.parseEther("99"));
  await tx.wait();
  
  console.log("Migration successful! Tx:", tx.hash);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
