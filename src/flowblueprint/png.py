"""Render the SVG drawing to PNG with the optional resvg renderer.

PNG output needs ``pip install "flowblueprint[png]"`` (resvg-py: prebuilt
wheels for Windows, macOS and Linux, nothing to compile). Every other
format works without it.
"""

PNG_HINT_STR = ('PNG output needs the optional renderer: '
                'pip install "flowblueprint[png]"')
PNG_ZOOM_FLOAT = 2.0
PNG_BACKGROUND_STR = "#ffffff"


class PngUnavailableError(RuntimeError):
    """The optional PNG renderer is not installed."""


def render_png_bytes(svg_str: str) -> bytes:
    """Rasterise an SVG drawing at twice its size on a white background.

    Args:
        svg_str: The SVG text FlowBlueprint drew.

    Returns:
        The PNG file contents.

    Raises:
        PngUnavailableError: resvg-py is not installed.
    """
    try:
        import resvg_py
    except ImportError as error:
        raise PngUnavailableError(PNG_HINT_STR) from error
    return bytes(resvg_py.svg_to_bytes(svg_string=svg_str,
                                       background=PNG_BACKGROUND_STR,
                                       zoom=PNG_ZOOM_FLOAT))
