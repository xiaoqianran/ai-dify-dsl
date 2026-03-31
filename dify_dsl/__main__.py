"""Allow running as ``python -m dify_dsl``."""

from dify_dsl.cli import main
import sys

sys.exit(main())
