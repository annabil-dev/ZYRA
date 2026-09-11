import pytest
import os
from ai.tokenizer import MyAITokenizer

@pytest.fixture
def temp_corpus(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    
    file1 = corpus_dir / "sample1.txt"
    file1.write_text("Hello world! This is a simple test.", encoding="utf-8")
    
    file2 = corpus_dir / "sample2.txt"
    file2.write_text("Tokenizer tokenizer tokenizer. 🚗 Emoji!", encoding="utf-8")
    
    return str(corpus_dir)

def test_tokenizer_training(temp_corpus):
    tokenizer = MyAITokenizer()
    tokenizer.train(temp_corpus, vocab_size=300)  # slightly higher than 256 + 4
    
    # Check if vocabulary increased
    assert tokenizer.vocab.size() > 260
    assert len(tokenizer.merges) > 0

def test_tokenizer_encode_decode(temp_corpus):
    tokenizer = MyAITokenizer()
    tokenizer.train(temp_corpus, vocab_size=300)
    
    test_strings = [
        "Halo dunia!",
        "Selamat pagi, apa kabar?",
        "AI ini dibuat sendiri.",
        "Hello world!",
        'printf("Hello World\\n");',
        "std::vector<int> values = {1, 2, 3};",
        "def hello():\n    print('hello')",
        "STM32 + ROS 2 + CUDA",
        "1234567890",
        "!@#$%^&*()",
        "🙂🚗🤖🔥",
        "日本語",
        "한국어",
        "مرحبا",
        "你好",
        "\n\n",
        "    indentation",
        "Hello\nWorld",
        "Indonesia + English + C++ + ROS2 🚗"
    ]
    
    for text in test_strings:
        encoded = tokenizer.encode(text)
        decoded = tokenizer.decode(encoded)
        assert text == decoded, f"Roundtrip failed for: {text}"
