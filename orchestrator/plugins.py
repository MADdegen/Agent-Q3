"""
Agent-Q3 — Plugin auto-loader.

Plugins are drop-in FastAPI router modules placed under /app/plugins/<name>/.
Each plugin directory must contain a `plugin.py` that exposes either:
  - `router: APIRouter`           — auto-mounted at /plugins/<name>/...
  - `register(app: FastAPI)`      — called with the host app for custom wiring

Plugins are discovered at service startup. A `manifest.json` is optional but
recommended; if present its keys are exposed at /plugins/list.
"""

import importlib.util
import json
from pathlib import Path
from typing import Callable, Optional

import structlog
from fastapi import FastAPI, APIRouter

log = structlog.get_logger(__name__)

PLUGINS_DIR = Path("/app/plugins")


class Plugin:
    __slots__ = ("name", "manifest", "module", "router", "register_fn", "path")

    def __init__(self, name: str, manifest: dict, module,
                 router: APIRouter | None, register_fn: Callable | None,
                 path: str):
        self.name = name
        self.manifest = manifest
        self.module = module
        self.router = router
        self.register_fn = register_fn
        self.path = path

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "manifest": self.manifest,
            "has_router": self.router is not None,
            "has_register_fn": self.register_fn is not None,
            "path": self.path,
        }


class PluginRegistry:
    def __init__(self, plugins_dir: Path = PLUGINS_DIR):
        self.plugins_dir = plugins_dir
        self._plugins: list[Plugin] = []

    def discover(self) -> int:
        self._plugins.clear()
        if not self.plugins_dir.exists():
            log.info("plugins directory missing — none loaded", path=str(self.plugins_dir))
            return 0

        for child in sorted(self.plugins_dir.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            plugin_py = child / "plugin.py"
            if not plugin_py.exists():
                continue
            try:
                plug = self._load(child, plugin_py)
                if plug:
                    self._plugins.append(plug)
            except Exception as e:
                log.warning("plugin load failed", name=child.name, error=str(e))

        log.info("plugins discovered", count=len(self._plugins),
                 names=[p.name for p in self._plugins])
        return len(self._plugins)

    @staticmethod
    def _load(plugin_dir: Path, plugin_py: Path) -> Optional[Plugin]:
        manifest = {}
        mf = plugin_dir / "manifest.json"
        if mf.exists():
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                pass

        name = manifest.get("name", plugin_dir.name)
        spec = importlib.util.spec_from_file_location(
            f"agent_q3_plugin_{name}", str(plugin_py)
        )
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        router = getattr(module, "router", None)
        register_fn = getattr(module, "register", None)
        if not (isinstance(router, APIRouter) or callable(register_fn)):
            log.warning("plugin has no router or register()", name=name)
            return None

        return Plugin(name, manifest, module, router, register_fn, str(plugin_dir))

    def mount_into(self, app: FastAPI) -> int:
        mounted = 0
        for p in self._plugins:
            try:
                if p.router is not None:
                    app.include_router(p.router, prefix=f"/plugins/{p.name}",
                                       tags=[f"plugin:{p.name}"])
                    mounted += 1
                if callable(p.register_fn):
                    p.register_fn(app)
                    mounted += 1
            except Exception as e:
                log.error("plugin mount failed", name=p.name, error=str(e))
        log.info("plugins mounted", count=mounted)
        return mounted

    @property
    def all(self) -> list[Plugin]:
        return list(self._plugins)


plugins = PluginRegistry()
