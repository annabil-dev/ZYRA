import bz2
import json
import logging
import re
from typing import Generator, Dict, Any, Optional
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

class WikiExtractor:
    """
    Streaming extractor for Wikipedia XML BZ2 dumps.
    Avoids loading the entire XML into RAM.
    """
    
    @staticmethod
    def _clean_wikitext(text: str) -> str:
        """
        Ultra-conservative wikitext cleaner.
        Removes heavy XML/Wiki markup but preserves natural language structure.
        """
        # Remove XML comments
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        # Remove templates {{...}} roughly
        text = re.sub(r'\{\{.*?\}\}', '', text, flags=re.DOTALL)
        # Remove infoboxes {|...|}
        text = re.sub(r'\{\|.*?\|\}', '', text, flags=re.DOTALL)
        # Remove [[Category:X]], [[File:X]], [[Image:X]]
        text = re.sub(r'\[\[(?:Category|Kategori|File|Berkas|Image|Gambar):.*?\]\]', '', text, flags=re.IGNORECASE)
        # Simplify [[link|text]] to text
        text = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', text)
        # Remove HTML tags roughly
        text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', '', text)
        # Remove multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    @staticmethod
    def extract_stream(bz2_filepath: str, language: str = "id", source_id: str = "wiki") -> Generator[Dict[str, Any], None, None]:
        """
        Yields documents one by one from a bz2 XML dump.
        """
        logger.info(f"Starting streaming extraction from {bz2_filepath}")
        
        try:
            with bz2.open(bz2_filepath, "rt", encoding="utf-8") as f:
                context = ET.iterparse(f, events=("start", "end"))
                
                in_page = False
                title = ""
                doc_id = ""
                ns = ""
                
                # Get namespace from root tag
                _, root = next(context)
                ns_match = re.match(r'\{.*\}', root.tag)
                ns_prefix = ns_match.group(0) if ns_match else ""
                
                for event, elem in context:
                    if event == "end" and elem.tag == f"{ns_prefix}page":
                        # We have a full page
                        title_elem = elem.find(f"{ns_prefix}title")
                        id_elem = elem.find(f"{ns_prefix}id")
                        ns_elem = elem.find(f"{ns_prefix}ns")
                        revision = elem.find(f"{ns_prefix}revision")
                        
                        if title_elem is not None and id_elem is not None and revision is not None:
                            # Only parse main namespace (ns == 0)
                            if ns_elem is not None and ns_elem.text == "0":
                                text_elem = revision.find(f"{ns_prefix}text")
                                if text_elem is not None and text_elem.text:
                                    raw_text = text_elem.text
                                    clean_text = WikiExtractor._clean_wikitext(raw_text)
                                    
                                    if clean_text and len(clean_text) > 100: # Minimum useful length
                                        yield {
                                            "id": f"{source_id}_{id_elem.text}",
                                            "source": source_id,
                                            "language": language,
                                            "title": title_elem.text,
                                            "text": clean_text
                                        }
                        
                        # Free memory! CRITICAL for streaming large XMLs
                        elem.clear()
                        root.clear()
        except Exception as e:
            logger.error(f"Error during Wiki streaming: {e}")
            raise
