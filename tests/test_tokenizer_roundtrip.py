import pytest
from ai.tokenizer import MyAITokenizer

@pytest.fixture
def temp_corpus(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    file1 = corpus_dir / "sample.txt"
    file1.write_text("Determinism and roundtrip testing data. Testing determinism requires repeated runs.", encoding="utf-8")
    return str(corpus_dir)

def test_tokenizer_deterministic_training(temp_corpus):
    tokenizer1 = MyAITokenizer()
    tokenizer1.train(temp_corpus, vocab_size=300)
    
    tokenizer2 = MyAITokenizer()
    tokenizer2.train(temp_corpus, vocab_size=300)
    
    assert tokenizer1.merges == tokenizer2.merges
    assert tokenizer1.vocab.token_to_id == tokenizer2.vocab.token_to_id

def test_tokenizer_load_roundtrip(temp_corpus, tmp_path):
    tokenizer = MyAITokenizer()
    tokenizer.train(temp_corpus, vocab_size=300)
    
    save_dir = str(tmp_path / "model")
    tokenizer.save(save_dir)
    
    loaded = MyAITokenizer.load(save_dir)
    
    text = "Testing determinism requires repeated runs."
    encoded = loaded.encode(text)
    decoded = loaded.decode(encoded)
    
    assert text == decoded
