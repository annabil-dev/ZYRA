import pytest
import os
import logging
from ai.tokenizer.tokenizer import MyAITokenizer
from ai.dataset.builder import DatasetBuilder
from ai.dataset.reader import DatasetReader
from ai.dataset.metadata import DatasetMetadata

@pytest.fixture
def dummy_dataset(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "sample.txt").write_text("Hello testing validation", encoding="utf-8")
    
    tok = MyAITokenizer()
    tok.train(str(corpus_dir), vocab_size=300)
    
    output_dir = str(tmp_path / "dataset")
    config = {"split_ratio": {"train": 1.0, "validation": 0.0, "test": 0.0}, "random_seed": 42}
    builder = DatasetBuilder(tok, config, logging.getLogger("test"))
    builder.build(str(corpus_dir), output_dir)
    
    return output_dir, tok

def test_tokenizer_compatibility_check(dummy_dataset):
    dataset_dir, tok1 = dummy_dataset
    
    # Create a completely different tokenizer
    tok2 = MyAITokenizer()
    tok2.vocab.add_token("DIFFERENT_TOKEN") # change vocab to produce different hash
    
    # Attempting to read should raise ValueError
    with pytest.raises(ValueError, match="Tokenizer mismatch"):
        reader = DatasetReader(dataset_dir, tok2)

def test_truncated_binary_detection(dummy_dataset):
    dataset_dir, tok = dummy_dataset
    
    # Corrupt binary file by truncating 1 byte
    train_bin = os.path.join(dataset_dir, "train.bin")
    with open(train_bin, "ab") as f:
        f.truncate(os.path.getsize(train_bin) - 1)
        
    with pytest.raises(ValueError, match="Truncated binary file"):
        reader = DatasetReader(dataset_dir, tok)
