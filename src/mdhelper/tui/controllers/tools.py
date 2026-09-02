"""Terminal integration, template, and configuration workflows."""

from __future__ import annotations

from mdhelper.tui.controllers.base import ControllerContext


class ToolController(ControllerContext):
    def _tools(self) -> None:
        while True:
            choice = self.terminal.menu(
                "Tools",
                (
                    ("Integrations", "1"),
                    ("Templates", "2"),
                    ("Configuration summary", "3"),
                ),
            )
            if choice is None:
                return
            if choice == "1":
                self._integrations()
            elif choice == "2":
                self._templates()
            else:
                self._config()

    def _integrations(self) -> None:
        names = self.application.integrations.names()
        while True:
            options = tuple(
                (f"Detect {name}", str(number))
                for number, name in enumerate(names, 1)
            )
            choice = self.terminal.menu("Integrations", options)
            if choice is None:
                return
            name = names[int(choice) - 1]
            status = self.application.integrations.detect(name)
            self.terminal.heading(f"{name} detection")
            availability = "available" if status.available else "unavailable"
            self.terminal.write(
                f"{status.path or 'not found'} | {availability} | "
                f"{status.version or 'unknown'}"
            )
            if status.capabilities:
                self.terminal.write(f"  capabilities: {', '.join(status.capabilities)}")
            if status.error:
                self.terminal.write(f"  {status.error}")

    def _templates(self) -> None:
        while True:
            templates = self.application.templates.list()
            choice = self.terminal.menu(
                "Templates",
                tuple(
                    (f"{item.category} / {item.title}", str(number))
                    for number, item in enumerate(templates, 1)
                ),
            )
            if choice is None:
                return
            template = templates[int(choice) - 1]
            self.terminal.heading(template.title)
            self.terminal.write(template.content)

    def _config(self) -> None:
        config = self.application.config
        self.terminal.heading("Resolved configuration")
        self.terminal.write(f"Path: {self.application.config_file}")
        self.terminal.write(
            f"Maximum pairs per chunk: {config.resources.max_pairs_per_chunk}"
        )
        self.terminal.write(f"GUI theme: {config.gui.theme}")
        self.terminal.write(f"GUI font size: {config.gui.font_size:g} pt")
        self.terminal.write("Configured integrations:")
        for name, item in sorted(config.integrations.items()):
            self.terminal.write(
                f"  {name}: {'enabled' if item.enabled else 'disabled'}, "
                f"path: {item.path or 'automatic detection'}"
            )
