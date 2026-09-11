class ByteCodec:
    """
    Handles mapping of raw bytes (0-255) to a stable set of Unicode characters.
    This ensures that all bytes can be represented as strings and merged without
    control character or whitespace issues.
    """
    def __init__(self):
        self.byte_encoder = self._build_byte_encoder()
        self.byte_decoder = {v: k for k, v in self.byte_encoder.items()}

    def _build_byte_encoder(self):
        """
        Returns a dictionary mapping byte values (0-255) to Unicode characters.
        Printable ASCII characters and standard latin-1 characters are kept as is.
        Control characters and spaces are mapped to higher Unicode points.
        """
        # Printable ascii + latin-1 extensions
        bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
        cs = bs[:]
        n = 0
        for b in range(2**8):
            if b not in bs:
                bs.append(b)
                cs.append(2**8 + n)
                n += 1
        
        cs = [chr(n) for n in cs]
        return dict(zip(bs, cs))

    def encode_bytes(self, data: bytes) -> str:
        """Converts raw bytes to the internal string representation."""
        return "".join(self.byte_encoder[b] for b in data)

    def decode_string(self, text: str) -> bytes:
        """Converts the internal string representation back to raw bytes."""
        return bytes(self.byte_decoder[c] for c in text)
