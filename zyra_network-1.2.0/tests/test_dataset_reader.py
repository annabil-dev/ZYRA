import pytest
import os
import json
import logging
import numpy as np
from ai.tokenizer.tokenizer import MyAITokenizer
from ai.dataset.builder import DatasetBuilder
from ai.dataset.reader import DatasetReader

@pytest.fixture
def temp_dataset(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    
    for i in range(20):
        (corpus_dir / f"doc_{i}.txt").write_text(f"This is a long document number {i} for testing context window sampling. We need enough tokens.", encoding="utf-8")
        
    tok = MyAITokenizer()
    tok.train(str(corpus_dir), vocab_size=300)
    
    output_dir = str(tmp_path / "dataset")
    
    config = {"split_ratio": {"train": 1.0, "validation": 0.0, "test": 0.0}, "random_seed": 42}
    builder = DatasetBuilder(tok, config, logging.getLogger("test"))
    builder.build(str(corpus_dir), output_dir)
    
    return output_dir, tok

def test_dataset_reader_loading_and_sampling(temp_dataset):
    dataset_dir, tok = temp_dataset
    
    reader = DatasetReader(dataset_dir, tok)
    assert reader.dtype == np.uint16
    assert "train" in reader.memmaps
    
    # Test document retrieval
    doc_tokens = reader.get_document("train", 0)
    assert isinstance(doc_tokens, list)
    assert len(doc_tokens) > 0
    assert doc_tokens[-1] == tok.vocab.get_id(tok.config.get("special_tokens", {}).get("eos", "<|eos|>"))
    
    # Test batch sampling (context length 5, batch size 2)
    X, Y = reader.get_batch("train", batch_size=2, context_length=5)
    
    assert X.shape == (2, 5)
    assert Y.shape == (2, 5)
    
    # Y should be X shifted by 1 (we can't easily assert exactly shifted here since we randomize,
    # but we can check memory manually if we fixed the seed or just know that by design Y is shifted).
    # Since reader uses same chunk: X is chunk[0:5], Y is chunk[1:6]
    # So X[0][1:] == Y[0][:-1]
    assert np.array_equal(X[0][1:], Y[0][:-1])
