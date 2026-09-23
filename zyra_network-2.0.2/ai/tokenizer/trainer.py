import os
import glob
from typing import Dict, Tuple, Any
import logging

from ai.tokenizer.byte_codec import ByteCodec
from ai.tokenizer.bpe import BPE
from ai.tokenizer.vocabulary import Vocabulary

class TokenizerTrainer:
    """
    Handles the training loop for the Byte-Level BPE tokenizer.
    """
    def __init__(self, vocab: Vocabulary, logger: logging.Logger):
        self.vocab = vocab
        self.logger = logger
        self.merges: Dict[Tuple[str, str], int] = {}
        self.byte_codec = self.vocab.byte_codec

    def train(self, corpus_dir: str, target_vocab_size: int, min_frequency: int = 2) -> Dict[Tuple[str, str], int]:
        """
        Trains the tokenizer on all .txt files in the given corpus directory.
        Returns the trained merges dictionary.
        """
        if not os.path.exists(corpus_dir):
            self.logger.error(f"Corpus directory not found: {corpus_dir}")
            raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")
            
        txt_files = glob.glob(os.path.join(corpus_dir, "*.txt"))
        if not txt_files:
            self.logger.warning(f"No .txt files found in {corpus_dir}")
            raise ValueError(f"No tokenizer training corpus found in {corpus_dir}")

        self.logger.info(f"Starting tokenizer training. Corpus documents: {len(txt_files)}")
        
        # 1. Read Corpus and pre-tokenize into word frequencies (using basic split or just processing per file)
        # For true byte-level BPE without a pre-tokenizer (like regex), we treat the whole file as a sequence of bytes,
        # but to make it tractable we can split by whitespace or newline if we want. 
        # However, to be purely byte-level without losing spaces, we should encode bytes and maybe split on whitespace 
        # while keeping the whitespace character as part of the token, or just count the entire string.
        # To avoid OOM and keep it simple, we split by spaces/newlines but retain them. 
        # For MY-AI, let's use a very simple whitespace-aware splitting (similar to basic gpt2 pre-tokenization).
        import re
        # A simpler fallback regex since standard 're' doesn't support \p
        fallback_pat = re.compile(r"""'s|'t|'re|'ve|'m|'ll|'d| ?[a-zA-Z]+| ?[0-9]+| ?[^\s0-9a-zA-Z]+|\s+(?!\S)|\s+""")
        
        word_freqs = {}
        total_bytes = 0
        
        for file_path in txt_files:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
                raw_bytes = text.encode("utf-8")
                total_bytes += len(raw_bytes)
                
                # We simply split into "words" using the fallback pattern
                words = fallback_pat.findall(text)
                for w in words:
                    # encode string to raw bytes, then to our byte_codec string
                    w_bytes = w.encode("utf-8")
                    encoded_word = self.byte_codec.encode_bytes(w_bytes)
                    
                    word_tuple = tuple(encoded_word)
                    word_freqs[word_tuple] = word_freqs.get(word_tuple, 0) + 1

        self.logger.info(f"Corpus bytes: {total_bytes}")
        self.logger.info(f"Target vocabulary: {target_vocab_size}")
        
        # We start with the base vocabulary size
        num_merges = target_vocab_size - self.vocab.size()
        if num_merges <= 0:
            self.logger.warning("Target vocab size is smaller or equal to base vocab. No merges needed.")
            return self.merges

        # 2. BPE Merge Loop
        for i in range(num_merges):
            pairs = BPE.get_stats(word_freqs)
            if not pairs:
                break
            
            # Find the best pair. 
            # Deterministic tie-breaker: sort by count (descending), then alphabetically (ascending)
            # max() takes a single key. We return (count, -lexical_val) to get highest count, lowest lexical
            best_pair = max(pairs.items(), key=lambda item: (item[1], item[0][0], item[0][1]))
            
            pair, count = best_pair
            
            if count < min_frequency:
                self.logger.info(f"Stopping early. Max frequency {count} < min_frequency {min_frequency}")
                break
                
            # Merge and add to vocab
            self.merges[pair] = i
            merged_token = pair[0] + pair[1]
            self.vocab.add_token(merged_token)
            
            # Update word freqs
            word_freqs = BPE.merge_vocab(pair, word_freqs)
            
            if (i + 1) % 100 == 0 or i == num_merges - 1:
                self.logger.info(f"Merge {i+1} / {num_merges} : {pair} -> {merged_token} (Freq: {count})")
                
        self.logger.info("Training completed.")
        return self.merges
