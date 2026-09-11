import pytest
import os
import json
import logging
from ai.tokenizer.tokenizer import MyAITokenizer
from ai.dataset.builder import DatasetBuilder
from ai.dataset.document import DocumentReader

@pytest.fixture
def temp_corpus(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    
    file1 = corpus_dir / "sample1.txt"
    file1.write_text("This is test document one.", encoding="utf-8")
    
    file2 = corpus_dir / "sample2.jsonl"
    file2.write_text(json.dumps({"text": "JSONL document one"}) + "\n" +
                     json.dumps({"text": "JSONL document two"}), encoding="utf-8")
    
    return str(corpus_dir)

@pytest.fixture
def tokenizer(temp_corpus):
    tok = MyAITokenizer()
    tok.train(temp_corpus, vocab_size=300)
    return tok

def test_document_reader_parsing(temp_corpus):
    config = {"split_ratio": {"train": 1.0, "validation": 0.0, "test": 0.0}, "random_seed": 42}
    reader = DocumentReader(temp_corpus, config)
    
    docs = list(reader.read_documents())
    assert len(docs) == 3
    assert docs[0][0] == "train" # since train is 1.0

def test_dataset_builder_creation(temp_corpus, tmp_path, tokenizer):
    config = {"split_ratio": {"train": 0.6, "validation": 0.2, "test": 0.2}, "random_seed": 42}
    logger = logging.getLogger("test_logger")
    
    output_dir = str(tmp_path / "dataset_out")
    builder = DatasetBuilder(tokenizer, config, logger)
    builder.build(temp_corpus, output_dir)
    
    assert os.path.exists(os.path.join(output_dir, "metadata.json"))
    assert os.path.exists(os.path.join(output_dir, "manifest.json"))
    assert os.path.exists(os.path.join(output_dir, "statistics.json"))
    
    for s in ["train", "validation", "test"]:
        assert os.path.exists(os.path.join(output_dir, f"{s}.bin"))
        assert os.path.exists(os.path.join(output_dir, f"{s}.idx"))
