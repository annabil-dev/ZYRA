import pytest
from ai.tokenizer.byte_codec import ByteCodec

def test_byte_codec_mapping():
    codec = ByteCodec()
    
    # Ensure encoder size is 256
    assert len(codec.byte_encoder) == 256
    assert len(codec.byte_decoder) == 256
    
    # Test encoding decoding cycle
    original_bytes = bytes([0, 10, 32, 65, 255])
    encoded_str = codec.encode_bytes(original_bytes)
    
    assert isinstance(encoded_str, str)
    assert len(encoded_str) == len(original_bytes)
    
    decoded_bytes = codec.decode_string(encoded_str)
    assert original_bytes == decoded_bytes

def test_byte_codec_utf8_roundtrip():
    codec = ByteCodec()
    original_text = "Halo dunia! 🚗 🔥"
    raw_bytes = original_text.encode("utf-8")
    
    encoded_str = codec.encode_bytes(raw_bytes)
    decoded_bytes = codec.decode_string(encoded_str)
    
    decoded_text = decoded_bytes.decode("utf-8")
    assert original_text == decoded_text
