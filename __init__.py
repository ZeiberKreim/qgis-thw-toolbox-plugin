def classFactory(iface):
    from .src.plugin import THWToolboxPlugin

    return THWToolboxPlugin(iface)
