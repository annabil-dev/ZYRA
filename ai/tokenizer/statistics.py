class TokenizerStatistics:
    """
    Computes statistics about the text and tokenization process.
    """
    @staticmethod
    def calculate(text: str, token_ids: list[int]) -> dict:
        char_count = len(text)
        utf8_bytes = len(text.encode("utf-8"))
        token_count = len(token_ids)
        
        compression_ratio = utf8_bytes / token_count if token_count > 0 else 0
        avg_bytes_per_token = utf8_bytes / token_count if token_count > 0 else 0
        
        return {
            "characters": char_count,
            "utf8_bytes": utf8_bytes,
            "tokens": token_count,
            "compression_ratio": round(compression_ratio, 2),
            "average_bytes_per_token": round(avg_bytes_per_token, 2)
        }
