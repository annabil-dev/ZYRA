import pytest
import os
from ai.tokenizer import MyAITokenizer

@pytest.fixture
def temp_corpus(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    file1 = corpus_dir / "sample.txt"
    file1.write_text("Hello tokenizer save load test. 🚗", encoding="utf-8")
    return str(corpus_dir)

def test_tokenizer_serialization(temp_corpus, tmp_path):
    tokenizer = MyAITokenizer()
    tokenizer.train(temp_corpus, vocab_size=300)
    
    save_dir = str(tmp_path / "saved_model")
    tokenizer.save(save_dir)
    
    assert os.path.exists(os.path.join(save_dir, "vocab.json"))
    assert os.path.exists(os.path.join(save_dir, "merges.json"))
    assert os.path.exists(os.path.join(save_dir, "tokenizer_config.yaml"))
    
    loaded_tokenizer = MyAITokenizer.load(save_dir)
    
    assert loaded_tokenizer.vocab.size() == tokenizer.vocab.size()
    assert len(loaded_tokenizer.merges) == len(tokenizer.merges)
    
    # Test encoding consistency
    text = "Hello tokenizer test 🚗"
    assert tokenizer.encode(text) == loaded_tokenizer.encode(text)
