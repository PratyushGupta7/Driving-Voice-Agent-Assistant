"""Opt-in live Azure. Default pytest ignores this file.

The product NLU is the phrase parser. Do not run this for the demo.
  uv run pytest tests/test_nlu_live_stress.py
"""

import pytest

pytestmark = pytest.mark.skip(reason="Azure NLU reverted; demo path is tests/test_scenario_stress.py")
