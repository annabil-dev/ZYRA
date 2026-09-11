import pytest
from ai.tokenizer.bpe import BPE

def test_get_stats():
    word_freqs = {
        ('l', 'o', 'w'): 5,
        ('l', 'o', 'w', 'e', 'r'): 2,
        ('n', 'e', 'w', 'e', 's', 't'): 6,
        ('w', 'i', 'd', 'e', 's', 't'): 3
    }
    
    stats = BPE.get_stats(word_freqs)
    
    # ('e', 's') should appear in newest (6) and widest (3) -> 9
    assert stats[('e', 's')] == 9
    
    # ('l', 'o') should appear in low (5) and lower (2) -> 7
    assert stats[('l', 'o')] == 7

def test_merge_vocab():
    word_freqs = {
        ('l', 'o', 'w'): 5,
        ('l', 'o', 'w', 'e', 'r'): 2
    }
    pair = ('l', 'o')
    
    new_freqs = BPE.merge_vocab(pair, word_freqs)
    
    assert ('lo', 'w') in new_freqs
    assert new_freqs[('lo', 'w')] == 5
    assert ('lo', 'w', 'e', 'r') in new_freqs
    assert new_freqs[('lo', 'w', 'e', 'r')] == 2

def test_encode_word():
    bpe_ranks = {
        ('l', 'o'): 0,
        ('lo', 'w'): 1,
        ('e', 'r'): 2
    }
    
    word = ['l', 'o', 'w', 'e', 'r', 's']
    # simulate the byte codec output by just passing string directly to encode_word logic. 
    # BPE._merge_word works on tuples
    # our encode_word takes a single string. Let's pass "lowers"
    encoded = BPE.encode_word("lowers", bpe_ranks)
    
    assert encoded == ['low', 'er', 's']
