import os
import requests
import hashlib
import logging
from typing import Optional
from tqdm import tqdm

logger = logging.getLogger(__name__)

class CorpusDownloader:
    """Downloads large corpus files with resume capability and hash verification."""
    
    @staticmethod
    def download(url: str, output_path: str, expected_sha256: Optional[str] = None, chunk_size: int = 1024 * 1024) -> str:
        """
        Downloads a file from a URL. Resumes if the file already exists but is incomplete.
        Returns the absolute path to the downloaded file.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        file_size = 0
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            
        # Get total size from server
        head_headers = {"User-Agent": "MY-AI-Corpus-Builder/0.1 (https://github.com/my-ai; bot@example.com) python-requests/2.31.0"}
        response = requests.head(url, headers=head_headers, allow_redirects=True)
        total_size = int(response.headers.get("content-length", 0))
        
        if file_size > 0 and file_size == total_size:
            logger.info(f"File already downloaded completely: {output_path}")
            if expected_sha256:
                if CorpusDownloader.verify_hash(output_path, expected_sha256):
                    return output_path
                else:
                    logger.warning("Hash mismatch on existing file. Redownloading from scratch.")
                    file_size = 0
                    os.remove(output_path)
            else:
                return output_path

        headers = {"Range": f"bytes={file_size}-"} if file_size > 0 else {}
        headers["User-Agent"] = "MY-AI-Corpus-Builder/0.1 (https://github.com/my-ai; bot@example.com) python-requests/2.31.0"
        
        logger.info(f"Downloading {url} to {output_path}")
        response = requests.get(url, headers=headers, stream=True, allow_redirects=True)
        response.raise_for_status()
        
        mode = "ab" if file_size > 0 else "wb"
        with open(output_path, mode) as f:
            with tqdm(total=total_size, initial=file_size, unit="B", unit_scale=True, desc=os.path.basename(output_path)) as pbar:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
                        
        if expected_sha256 and not CorpusDownloader.verify_hash(output_path, expected_sha256):
            raise ValueError(f"Hash verification failed for {output_path}")
            
        return output_path
        
    @staticmethod
    def verify_hash(filepath: str, expected_hash: str) -> bool:
        """Verifies the SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        logger.info(f"Verifying hash for {filepath}...")
        with open(filepath, "rb") as f:
            # Read in 4MB chunks
            for byte_block in iter(lambda: f.read(4096 * 1024), b""):
                sha256_hash.update(byte_block)
        
        actual_hash = sha256_hash.hexdigest()
        if actual_hash != expected_hash:
            logger.error(f"Hash mismatch! Expected: {expected_hash}, Got: {actual_hash}")
            return False
        return True
