import os
import requests
import json
import numpy as np

def extract_text(file_path: str) -> str:
    """Extracts text from a given file (PDF, DOCX, TXT, etc)."""
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    
    try:
        if ext == ".pdf":
            import fitz # PyMuPDF
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text()
        elif ext == ".docx":
            import docx
            doc = docx.Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
        else:
            # Assume text-like (txt, py, js, md)
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
    except Exception as e:
        print(f"Error extracting text from {file_path}: {e}")
        
    return text

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Splits text into overlapping chunks."""
    if not text:
        return []
        
    chunks = []
    text = text.replace('\n', ' ')
    length = len(text)
    
    if length <= chunk_size:
        return [text]
        
    start = 0
    while start < length:
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
        
    return chunks

def get_embeddings_ollama(chunks: list[str], model_name: str, base_url: str = "http://localhost:11434") -> list[np.ndarray]:
    """Generates embeddings using Ollama /api/embeddings."""
    embeddings = []
    
    for chunk in chunks:
        try:
            r = requests.post(
                f"{base_url}/api/embeddings",
                json={"model": model_name, "prompt": chunk},
                timeout=10
            )
            r.raise_for_status()
            data = r.json()
            emb = data.get("embedding", [])
            embeddings.append(np.array(emb, dtype=np.float32))
        except Exception as e:
            print(f"Embedding error: {e}")
            # Append zero vector if failed
            embeddings.append(np.zeros(4096, dtype=np.float32))
            
    return embeddings

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Computes cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return np.dot(a, b) / (norm_a * norm_b)

def retrieve_relevant_context(query: str, file_paths: list[str], model_name: str, top_k: int = 3, progress_callback=None) -> str:
    """
    Complete RAG pipeline for temporary attachments.
    Returns a formatted string containing the most relevant chunks.
    """
    all_chunks = []
    for fp in file_paths:
        if progress_callback:
            progress_callback(f"Extracting text from {os.path.basename(fp)}...")
            
        text = extract_text(fp)
        filename = os.path.basename(fp)
        if text:
            chunks = chunk_text(text, chunk_size=1500, overlap=300)
            for c in chunks:
                all_chunks.append({"filename": filename, "content": c})
                
    if not all_chunks:
        return ""
        
    if len(all_chunks) <= top_k:
        # Document is small enough, no need for embeddings
        context = "\n\n--- ATTACHED DOCUMENTS ---\n"
        for chunk in all_chunks:
            context += f"\nFile: {chunk['filename']}\n```\n{chunk['content']}\n```\n"
        context += "--------------------------\n"
        return context
        
    if progress_callback:
        progress_callback(f"Embedding prompt...")
        
    # Generate embeddings for query and chunks
    query_emb = get_embeddings_ollama([query], model_name)[0]
    
    if progress_callback:
        progress_callback(f"Embedding {len(all_chunks)} chunks for context search...")
        
    chunk_texts = [c["content"] for c in all_chunks]
    chunk_embs = get_embeddings_ollama(chunk_texts, model_name)
    
    # Calculate similarities
    scored_chunks = []
    for i, emb in enumerate(chunk_embs):
        sim = cosine_similarity(query_emb, emb)
        scored_chunks.append((sim, all_chunks[i]))
        
    # Sort by descending similarity
    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    top_chunks = scored_chunks[:top_k]
    
    context = "\n\n--- RELEVANT DOCUMENT CONTEXT (RAG) ---\n"
    for sim, chunk in top_chunks:
        context += f"\n[Score: {sim:.2f}] Source: {chunk['filename']}\n```\n{chunk['content']}\n```\n"
    context += "--------------------------------------\n"
    
    return context
