"""ComfyUI-RotoTools: transparent TGA zip saver and spec readout nodes for roto / alpha-matte workflows."""
if __package__:
    from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
else:  # imported as a bare module (pytest's package collector); real errors in nodes.py must still surface in ComfyUI
    NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS = {}, {}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
