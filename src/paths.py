import os


def plugin_root() -> str:
    """Absolute path to the plugin root directory (parent of src/).

    Used to locate resources that live outside the Python package: icons/,
    svgs/, metadata.txt, temp_files/. All modules should call this helper
    instead of computing dirname(__file__) themselves, since the depth
    relative to the plugin root depends on the module's location in src/.
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
