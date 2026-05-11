import configparser
import logging
import os

from qgis.core import Qgis, QgsMessageLog

from .paths import plugin_root

# All plugin messages appear under this tab in QGIS Log Messages panel
_PLUGIN_TAG = "THW Toolbox"
# Root of the plugin's logger hierarchy. All loggers returned from
# get_logger() are children of this name so a single handler config
# covers everything.
_ROOT_NAME = "thw_toolbox"
# Env var takes priority over config.ini — handy for ad-hoc debug sessions
# without touching files.
_LEVEL_ENV_VAR = "THW_TOOLBOX_LOG_LEVEL"
_CONFIG_FILENAME = "config.ini"
_DEFAULT_LEVEL = logging.ERROR

_LEVEL_MAP = {
    logging.DEBUG: Qgis.MessageLevel.Info,  # Qgis has no Debug level
    logging.INFO: Qgis.MessageLevel.Info,
    logging.WARNING: Qgis.MessageLevel.Warning,
    logging.ERROR: Qgis.MessageLevel.Critical,
    logging.CRITICAL: Qgis.MessageLevel.Critical,
}

_configured = False


class _QgsLogHandler(logging.Handler):
    """Forward Python logging records to the QGIS Log Messages panel."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            QgsMessageLog.logMessage(
                self.format(record),
                _PLUGIN_TAG,
                _LEVEL_MAP.get(record.levelno, Qgis.MessageLevel.Info),
            )
        except Exception:
            self.handleError(record)


def get_logger(name: str) -> logging.Logger:
    """Return a logger that emits to the QGIS "THW Toolbox" log tab.

    Pass `__name__` from the calling module — only the last segment is
    kept so log lines stay readable (e.g. "layer_manager" rather than
    the full dotted path including the plugin folder name).
    """
    _configure_once()
    short_name = name.rsplit(".", 1)[-1]
    return logging.getLogger(f"{_ROOT_NAME}.{short_name}")


def _configure_once() -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger(_ROOT_NAME)
    handler = _QgsLogHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    root.addHandler(handler)
    root.setLevel(_resolve_level())
    # Don't bubble up — Python's root logger would echo to stderr/stdout
    # and we'd see duplicate messages in QGIS' Python console.
    root.propagate = False
    _configured = True


def _resolve_level() -> int:
    """Pick the log level: env var wins, then config.ini, then INFO default.

    Unknown level names silently fall back to INFO so a typo never breaks
    the plugin's startup.
    """
    # Env override
    env_value = os.environ.get(_LEVEL_ENV_VAR)
    if env_value:
        return _level_from_name(env_value, _DEFAULT_LEVEL)

    # config.ini at plugin root
    config_path = os.path.join(plugin_root(), _CONFIG_FILENAME)
    if os.path.exists(config_path):
        parser = configparser.ConfigParser()
        try:
            parser.read(config_path, encoding="utf-8")
            return _level_from_name(parser.get("logging", "level", fallback=""), _DEFAULT_LEVEL)
        except Exception as e:
            # Malformed config shouldn't prevent the plugin from loading
            logging.getLogger(_ROOT_NAME).debug("Failed to read %s: %s", config_path, e)

    return _DEFAULT_LEVEL


def _level_from_name(name: str, fallback: int) -> int:
    value = logging.getLevelName(name.strip().upper())
    return value if isinstance(value, int) else fallback
