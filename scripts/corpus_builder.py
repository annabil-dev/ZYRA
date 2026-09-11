import os
import json
import logging
import argparse
import time
import datetime
from tqdm import tqdm

from ai.dataset.corpus.downloader import CorpusDownloader
from ai.dataset.corpus.extractor import WikiExtractor
from ai.dataset.corpus.cleaner import CorpusCleaner

def main():
    parser = argparse.ArgumentParser(description="Bootstrap ZYRA Corpus v0.1.0")
    parser.add_argument("--output-dir", type=str, default="data/corpus/zyra_corpus_v0.1.0", help="Output directory")
    parser.add_argument("--max-docs", type=int, default=50000, help="Maximum number of documents to extract")
    parser.add_argument("--skip-download", action="store_true", help="Skip downloading if file already exists locally")
    
    args = parser.parse_args()
    
    # We will use Python's built in logging to ensure compatibility
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger("corpus_builder")
    
    logger.info("Initializing ZYRA Production Corpus Bootstrap (Phase 2.5)")
    
    corpus_dir = args.output_dir
    raw_dir = os.path.join(corpus_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    
    # WIKIPEDIA INDONESIA (Targeting a small slice of latest pages-articles for bootstrapping)
    wiki_url = "https://dumps.wikimedia.org/idwiki/latest/idwiki-latest-pages-articles.xml.bz2"
    wiki_path = os.path.join(raw_dir, "idwiki-latest-pages-articles.xml.bz2")
    
    if not args.skip_download or not os.path.exists(wiki_path):
        logger.info(f"Downloading Indonesian Wikipedia Dump from {wiki_url}")
        try:
            # We don't hash verify Wikipedia latest because it updates frequently
            CorpusDownloader.download(wiki_url, wiki_path)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            logger.info("Please download the file manually and place it at: " + wiki_path)
            return
    else:
        logger.info(f"Using existing file: {wiki_path}")

    # PROCESSING PIPELINE
    output_jsonl = os.path.join(corpus_dir, "documents.jsonl")
    manifest_file = os.path.join(corpus_dir, "manifest.json")
    
    cleaner = CorpusCleaner()
    
    logger.info(f"Extracting and cleaning documents to {output_jsonl}")
    start_time = time.time()
    
    docs_written = 0
    total_bytes = 0
    
    with open(output_jsonl, "w", encoding="utf-8") as out_f:
        # Extract from Wiki
        wiki_stream = WikiExtractor.extract_stream(wiki_path, language="id", source_id="idwiki")
        
        for doc in wiki_stream:
            if docs_written >= args.max_docs:
                break
                
            accepted, clean_doc = cleaner.process_document(doc, is_technical=False)
            if accepted:
                json_str = json.dumps(clean_doc, ensure_ascii=False)
                out_f.write(json_str + "\n")
                
                docs_written += 1
                total_bytes += len(json_str.encode('utf-8'))
                
                if docs_written % 1000 == 0:
                    logger.info(f"Processed {docs_written} documents...")
                    
    elapsed = time.time() - start_time
    
    # Write Manifest
    stats = cleaner.get_stats()
    manifest = {
        "corpus_name": "ZYRA Corpus v0.1.0",
        "build_id": f"build_{int(time.time())}",
        "created_at": datetime.datetime.now().isoformat(),
        "sources": [
            {
                "source_id": "idwiki",
                "source_name": "Indonesian Wikipedia",
                "source_location": wiki_url,
                "language": "id"
            }
        ],
        "statistics": {
            "total_documents": docs_written,
            "total_raw_bytes": total_bytes,
            "cleaner_stats": stats,
            "processing_time_seconds": elapsed
        }
    }
    
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    logger.info("=== CORPUS BUILD COMPLETE ===")
    logger.info(f"Total Documents : {docs_written}")
    logger.info(f"Total Output Size: {total_bytes / (1024**2):.2f} MB")
    logger.info(f"Duplicates Rem. : {stats['rejected_duplicate']}")
    logger.info(f"Manifest written to {manifest_file}")
    
if __name__ == "__main__":
    main()
