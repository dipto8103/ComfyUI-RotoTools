"""ComfyUI-RotoTools: roto / alpha-matte helper nodes (TGA zip saver, spec readout, folder batch loader)."""
if __package__:
    from . import nodes as _nodes, batch as _batch
    NODE_CLASS_MAPPINGS = {**_nodes.NODE_CLASS_MAPPINGS, **_batch.NODE_CLASS_MAPPINGS}
    NODE_DISPLAY_NAME_MAPPINGS = {**_nodes.NODE_DISPLAY_NAME_MAPPINGS, **_batch.NODE_DISPLAY_NAME_MAPPINGS}
else:  # imported as a bare module (pytest's package collector); real errors must still surface inside ComfyUI
    NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS = {}, {}

WEB_DIRECTORY = "./web"  # preview grid on Load Video Batch (Folders)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
