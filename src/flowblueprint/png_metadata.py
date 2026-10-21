"""Store an editable draw.io document inside a rendered PNG image."""

from collections.abc import Iterator
import struct
from urllib.parse import quote
import zlib

PNG_SIGNATURE_BYTES = b"\x89PNG\r\n\x1a\n"


def make_png_chunk_bytes(kind_bytes: bytes, data_bytes: bytes) -> bytes:
    """Encode a PNG chunk with its standard length and checksum.

    Args:
        kind_bytes (bytes): Four-byte chunk type.
        data_bytes (bytes): Chunk payload.
    Returns:
        bytes: Complete encoded chunk.
    Warnings:
        This helper is for metadata, not for rasterizing images.
    """
    return (struct.pack(">I", len(data_bytes)) + kind_bytes + data_bytes
            + struct.pack(">I", zlib.crc32(kind_bytes + data_bytes)))


def read_png_chunks_iterable(
    png_bytes: bytes,
) -> Iterator[tuple[bytes, bytes, bytes]]:
    """Yield checked PNG chunk types, payloads and original encoded bytes.

    Args:
        png_bytes (bytes): Complete PNG to inspect without decoding pixels.
    Returns:
        Iterator: Chunk type, payload and original bytes in source order.
    Warnings:
        Exhaust the iterator to validate the end chunk and trailing bytes.
    """
    if not png_bytes.startswith(PNG_SIGNATURE_BYTES):
        raise ValueError("Expected a PNG signature")
    offset_int = len(PNG_SIGNATURE_BYTES)
    while offset_int + 12 <= len(png_bytes):
        length_int = struct.unpack_from(">I", png_bytes, offset_int)[0]
        end_int = offset_int + length_int + 12
        if end_int > len(png_bytes):
            break
        kind_bytes = png_bytes[offset_int + 4:offset_int + 8]
        data_bytes = png_bytes[offset_int + 8:end_int - 4]
        checksum_int = struct.unpack_from(">I", png_bytes, end_int - 4)[0]
        if checksum_int != zlib.crc32(kind_bytes + data_bytes):
            raise ValueError("Invalid PNG chunk checksum")
        if offset_int == 8 and (kind_bytes != b"IHDR" or length_int != 13):
            raise ValueError("PNG must start with a 13-byte IHDR chunk")
        if kind_bytes == b"IEND" and (length_int or end_int != len(png_bytes)):
            raise ValueError("Invalid PNG end chunk")
        yield kind_bytes, data_bytes, png_bytes[offset_int:end_int]
        if kind_bytes == b"IEND":
            return
        offset_int = end_int
    raise ValueError("PNG is truncated or lacks IEND")


def add_drawio_to_png_bytes(png_bytes: bytes, drawio_str: str) -> bytes:
    """Embed XML before IDAT, where the draw.io reader stops its search.

    Args:
        png_bytes (bytes): Rendered PNG with valid chunks.
        drawio_str (str): Complete, editable multi-page draw.io XML.
    Returns:
        bytes: PNG with one mxfile text chunk before the first IDAT.
    Warnings:
        Malformed PNGs are refused; no image pixels are altered.
    """
    chunks_list = [PNG_SIGNATURE_BYTES]
    payload_bytes = b"mxfile\0" + quote(drawio_str, safe="").encode("ascii")
    inserted_bool = False
    for kind_bytes, data_bytes, chunk_bytes in read_png_chunks_iterable(
        png_bytes
    ):
        if kind_bytes == b"IDAT" and not inserted_bool:
            chunks_list.append(make_png_chunk_bytes(b"tEXt", payload_bytes))
            inserted_bool = True
        if (kind_bytes in (b"tEXt", b"zTXt", b"iTXt")
                and data_bytes.partition(b"\0")[0]
                in (b"mxfile", b"mxGraphModel")):
            continue
        chunks_list.append(chunk_bytes)
    if not inserted_bool:
        raise ValueError("PNG lacks image data (IDAT)")
    return b"".join(chunks_list)
