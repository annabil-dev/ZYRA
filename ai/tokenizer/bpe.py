from typing import Dict, List, Tuple

class BPE:
    """
    Core BPE algorithms for counting pairs and merging them.
    """
    @staticmethod
    def get_stats(word_freqs: Dict[Tuple[str, ...], int]) -> Dict[Tuple[str, str], int]:
        """
        Counts the frequency of all adjacent pairs in the current word structures.
        """
        pairs = {}
        for word, freq in word_freqs.items():
            for i in range(len(word) - 1):
                pair = (word[i], word[i + 1])
                pairs[pair] = pairs.get(pair, 0) + freq
        return pairs

    @staticmethod
    def merge_vocab(pair: Tuple[str, str], word_freqs: Dict[Tuple[str, ...], int]) -> Dict[Tuple[str, ...], int]:
        """
        Merges the specified pair in all words within the vocabulary.
        Returns the updated word frequencies.
        """
        new_word_freqs = {}
        first, second = pair
        
        for word, freq in word_freqs.items():
            new_word = []
            i = 0
            while i < len(word):
                if i < len(word) - 1 and word[i] == first and word[i + 1] == second:
                    new_word.append(first + second)
                    i += 2
                else:
                    new_word.append(word[i])
                    i += 1
            new_word_freqs[tuple(new_word)] = freq
            
        return new_word_freqs

    @staticmethod
    def encode_word(word: str, bpe_ranks: Dict[Tuple[str, str], int]) -> List[str]:
        """
        Applies BPE merge rules to a single word string.
        """
        word_tuple = tuple(word)
        if len(word_tuple) == 1:
            return list(word_tuple)
            
        while True:
            pairs = BPE._get_pairs(word_tuple)
            if not pairs:
                break
                
            # Find the pair with the lowest rank (earliest merge)
            # If pair is not in ranks, it defaults to infinity
            bigram = min(pairs, key=lambda p: bpe_ranks.get(p, float('inf')))
            if bigram not in bpe_ranks:
                break
                
            word_tuple = BPE._merge_word(word_tuple, bigram)
            if len(word_tuple) == 1:
                break
                
        return list(word_tuple)

    @staticmethod
    def _get_pairs(word: Tuple[str, ...]) -> List[Tuple[str, str]]:
        pairs = []
        for i in range(len(word) - 1):
            pairs.append((word[i], word[i+1]))
        return pairs
        
    @staticmethod
    def _merge_word(word: Tuple[str, ...], pair: Tuple[str, str]) -> Tuple[str, ...]:
        new_word = []
        i = 0
        while i < len(word):
            if i < len(word) - 1 and word[i] == pair[0] and word[i+1] == pair[1]:
                new_word.append(pair[0] + pair[1])
                i += 2
            else:
                new_word.append(word[i])
                i += 1
        return tuple(new_word)
