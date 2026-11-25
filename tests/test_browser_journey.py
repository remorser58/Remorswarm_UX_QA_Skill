"""Browser-plan admission and evidence integrity; fixtures are not user studies."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/remorsearch-ux-qa"))
from uxpersonas import local_run, workspace
from uxresearch.canonical import EngineError, canonical
from uxresearch.storage import atomic

_spec = importlib.util.spec_from_file_location("browser_fixture", ROOT / "skills/remorsearch-ux-qa/examples/journey/browser_fixture.py")
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


class BrowserJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.__dict__.update(fixture.build(self.root / "case"))
        workspace.prepare(self.source, self.work, reviewed_files=fixture.FILES)

    def test_reviewed_browser_plan_enters_existing_persona_pipeline(self):
        plan = local_run._plan(self.plan_path, workspace._state(self.work))
        self.assertEqual(plan["schema_version"], "ux-journey-browser-plan.v1")
        self.assertEqual(plan["runner"], "browser-adapter.json")
        self.assertFalse((self.work / local_run.MARKER).exists())


if __name__ == "__main__":
    unittest.main()
