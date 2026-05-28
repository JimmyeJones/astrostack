"""Allow ``python -m seestack`` to launch the GUI."""

from seestack.gui.main import main

if __name__ == "__main__":
    raise SystemExit(main())
