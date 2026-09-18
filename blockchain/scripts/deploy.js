const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying contracts with the account:", deployer.address);

  const token = await hre.ethers.deployContract("ZyraToken");
  await token.waitForDeployment();

  console.log("ZYRA Token deployed to:", await token.getAddress());
  
  // Verify developer balance
  const devBalance = await token.balanceOf(deployer.address);
  console.log("Developer Balance:", hre.ethers.formatEther(devBalance), "ZYRA");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
