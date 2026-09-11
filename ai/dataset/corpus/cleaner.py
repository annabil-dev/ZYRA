import hashlib
import re
import logging
from typing import Dict, Any, Set, Tuple

logger = logging.getLogger(__name__)

class CorpusCleaner:
    """
    Cleans, deduplicates, and validates documents.
    Provides safety scans for technical/code data.
    """
    
    def __init__(self):
        self.seen_hashes: Set[str] = set()
        self.stats = {
            "processed": 0,
            "rejected_length": 0,
            "rejected_duplicate": 0,
            "rejected_secrets": 0
        }
        
    def _normalize_for_hash(self, text: str) -> str:
        """Normalizes text strictly for deduplication purposes."""
        # Lowercase, remove all non-alphanumeric, squish whitespace
        normalized = re.sub(r'[^a-z0-9]', '', text.lower())
        return normalized

    def _hash_text(self, normalized_text: str) -> str:
        return hashlib.md5(normalized_text.encode('utf-8')).hexdigest()

    def _scan_secrets(self, text: str) -> bool:
        """
        Returns True if a secret/key is found, False otherwise.
        Very conservative scanner.
        """
        # AWS Keys, Generic API keys, private keys
        patterns = [
            r'AKIA[0-9A-Z]{16}',
            r'-----BEGIN (?:RSA )?PRIVATE KEY-----',
            r'(?:api_key|apikey|secret_key|password)["\']?\s*[:=]\s*["\'][a-zA-Z0-9\-_]{16,}["\']'
        ]
        
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return True
        return False

    def process_document(self, doc: Dict[str, Any], is_technical: bool = False) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Returns (is_accepted, cleaned_doc).
        Maintains internal deduplication state.
        """
        self.stats["processed"] += 1
        
        text = doc.get("text", "")
        
        # 1. Length Check
        if len(text.strip()) < 50:
            self.stats["rejected_length"] += 1
            return False, None
            
        # 2. Secret Scan (Only strictly needed for local technical files, but good everywhere)
        if is_technical and self._scan_secrets(text):
            self.stats["rejected_secrets"] += 1
            logger.warning(f"Rejected technical document due to potential secret/key: {doc.get('id', 'unknown')}")
            return False, None
            
        # 3. Deduplication
        normalized = self._normalize_for_hash(text)
        if not normalized: # Edge case: document was all symbols/spaces
            self.stats["rejected_length"] += 1
            return False, None
            
        doc_hash = self._hash_text(normalized)
        if doc_hash in self.seen_hashes:
            self.stats["rejected_duplicate"] += 1
            return False, None
            
        self.seen_hashes.add(doc_hash)
        
        return True, doc

    def get_stats(self) -> Dict[str, int]:
        return self.stats
