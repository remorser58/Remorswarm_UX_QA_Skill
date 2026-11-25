"""Repeated component warnings retain every element's measured evidence."""

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import _paths  # noqa: F401
from ergoqa import analyze, bundle, cli, report, swarm
from ergoqa.profiles import sample_profiles
from test_ergo_pipeline import el, make_run


class WarningGroups(unittest.TestCase):
    def capture(self, *, different_screen=False):
        profiles = sample_profiles(1, 7, ["galaxy-s24"])
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = make_run(Path(tmp))
            for index, path in enumerate(sorted(run_dir.glob("S-*.json"))):
                snap = json.loads(path.read_text())
                snap["surface"]["scroll"] = {"x": 0, "y": index * 300}
                snap["surface"]["visual"] = {"offsetTop": index * 20, "pageTop": index * 300}
                snap["elements"] = [
                    el("heading", "heading", (10, 10, 300, 30),
                       text="Edit" if index and different_screen else "Choose"),
                    *[
                        dict(el(f"choice-{i}", "button", (10 + i % 8 * 35, 100 + i // 8 * 40, 20, 20),
                                interactive=True, tag="button", text=str(i)),
                             selector_family="#choices > button.choice")
                        for i in range(47)
                    ],
                    dict(el("help", "button", (300, 500, 20, 20), interactive=True, tag="button", text="Help"),
                         selector_family="#tools > button.help"),
                    *[
                        dict(el(f"copy-{i}", "text", (10, 550 + i * 25, 250, 20), text=f"Detail {i}", fg="#aaaaaa"),
                             selector_family="#details > p.detail")
                        for i in range(3)
                    ],
                ]
                path.write_text(json.dumps(snap))
            result = analyze.analyze_run(run_dir, profiles, gaze_enabled=False)
        return profiles, result

    def test_repeated_geometry_and_readability_group_without_losing_evidence(self):
        profiles, result = self.capture()
        original = copy.deepcopy(result)
        findings = swarm.aggregate([result], profiles)
        small = [f for f in findings if f["check_id"] == "PT-02"]
        self.assertEqual(len(small), 2)
        repeated = next(f for f in small if len(f["selectors"]) == 47)
        self.assertEqual(repeated["element_count"], 47)
        self.assertEqual(len(repeated["examples"]), 3)
        self.assertEqual(len(repeated["observation_ids"]), 47)
        self.assertIn("47", repeated["summary_ko"])
        self.assertEqual(next(f for f in small if f is not repeated)["selectors"], ["#help"])
        text = [f for f in findings if f["check_id"] == "PC-01"]
        self.assertEqual(len(text), 1)
        self.assertEqual(text[0]["element_count"], 3)
        self.assertEqual(result, original)
        exported = bundle.to_evidence_bundle("B-groups", [result], findings, profiles)
        grouped_export = next(f for f in exported["records"]["findings"] if f["swarm_finding_id"] == repeated["id"])
        self.assertEqual(grouped_export["element_count"], 47)
        self.assertEqual(len(grouped_export["examples"]), 3)
        evidence = {o["id"]: o for o in exported["records"]["observations"]}
        self.assertEqual({evidence[oid]["element_key"] for oid in repeated["observation_ids"]},
                         {f"#choice-{i}|{i}" for i in range(47)})
        self.assertTrue(all(evidence[oid]["measurement"] for oid in repeated["observation_ids"]))
        self.assertIn("47", report.render(findings, profiles, [result], list_threshold="P3"))

    def test_different_screens_stay_distinct_even_with_the_same_selectors(self):
        profiles, result = self.capture(different_screen=True)
        findings = [f for f in swarm.aggregate([result], profiles) if f["check_id"] == "PT-02"]
        self.assertEqual(len(findings), 4)
        repeated = [f for f in findings if f["element_count"] == 47]
        self.assertEqual(len(repeated), 2)
        self.assertNotEqual(repeated[0]["screen_key"], repeated[1]["screen_key"])
        self.assertEqual(len(swarm.units(findings)), 4)

    def test_missing_family_does_not_guess_from_numbered_ids(self):
        profiles, result = self.capture()
        for obs in result["observations"]:
            obs.get("extra", {}).pop("warning_group", None)
        findings = [f for f in swarm.aggregate([result], profiles) if f["check_id"] == "PT-02"]
        self.assertEqual(len(findings), 48)

    def test_same_family_keeps_different_semantic_components_separate(self):
        profiles, result = self.capture()
        for obs in result["observations"]:
            if obs["element_key"].startswith("#choice-0|"):
                obs["extra"]["warning_group"]["roles"] = ["destructive"]
        findings = [f for f in swarm.aggregate([result], profiles) if f["check_id"] == "PT-02"]
        self.assertEqual(sorted(f["element_count"] for f in findings), [1, 1, 46])
        self.assertEqual(len(swarm.units(findings)), 3)

    def test_profile_export_counts_only_its_linked_elements_and_keeps_worst_severity(self):
        profiles, result = self.capture()
        other = copy.deepcopy(profiles[0])
        other["profile_id"] = "EP-other"
        profiles.append(other)
        result["profiles_evaluated"].append("EP-other")
        obs = copy.deepcopy(next(o for o in result["observations"]
                                 if o["check_id"] == "PT-02" and o["element_key"].startswith("#choice-0|")))
        obs.update(id="OB-other", profile_id="EP-other", severity="P1")
        result["observations"].append(obs)
        findings = swarm.aggregate([result], profiles)
        grouped = next(f for f in findings if f["check_id"] == "PT-02" and f["element_count"] == 47)
        self.assertEqual(grouped["severity"], "P1")
        self.assertEqual(len(grouped["observation_ids"]), 48)
        self.assertEqual(grouped["triggered_profiles"], ["EP-01", "EP-other"])
        exported = bundle.to_evidence_bundle("B-profiles", [result], findings, profiles)
        own = next(f for f in exported["records"]["findings"] if f["id"] == grouped["id"] + "@EP-other")
        self.assertEqual(own["element_count"], 1)
        self.assertEqual(own["examples"], ["#choice-0"])
        self.assertNotIn("47개", own["summary"])
        self.assertEqual(own["observation_ids"], ["OB-other"])

    def test_hypothesis_report_uses_element_count_not_finding_count(self):
        profiles, result = self.capture()
        observations = [o for o in result["observations"] if o["check_id"] == "PC-01"]
        for obs in observations:
            obs.update(check_id="PC-05", basis="model", epistemic_status="inferred")
        result["observations"] = observations
        findings = swarm.aggregate([result], profiles)
        self.assertEqual(len(findings), 1)
        rendered = report.render(findings, profiles, [result])
        self.assertIn("요소 3개", rendered)
        self.assertIn("#copy-0, #copy-1, #copy-2", rendered)

    def test_states_and_record_ids_of_one_screen_share_a_reach_group(self):
        profiles = sample_profiles(1, 7, ["galaxy-s24"])
        self.assertEqual(profiles[0]["attributes"]["grip"], "one_hand_right")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = make_run(Path(tmp))
            for index, path in enumerate(sorted(run_dir.glob("S-*.json"))):
                snap = json.loads(path.read_text())
                # Each state of the same booking screen has a new record ID and new controls.
                snap["surface"]["url"] = f"http://127.0.0.1:4318/booking/{1000 + index}?step=2#NB{77 + index}"
                snap["elements"] = [
                    el("heading", "heading", (10, 40, 300, 30), text="Booking"),
                    dict(el("account", "link", (330, 8, 24, 24), interactive=True, tag="a", text="Me", roles=("primary",)),
                         selector_family="header > a.account"),
                    *([el("toast", "status", (10, 700, 300, 40), text="Saved"),
                       el("undo", "button", (320, 700, 40, 40), interactive=True, tag="button", text="Undo")] if index else []),
                ]
                path.write_text(json.dumps(snap))
            result = analyze.analyze_run(run_dir, profiles, gaze_enabled=False)
        screens = {json.dumps(o["extra"]["screen"], sort_keys=True) for o in result["observations"] if o["snapshot_id"]}
        self.assertEqual(len(screens), 1)
        screen = json.loads(screens.pop())
        self.assertEqual(screen["route"], "http://127.0.0.1:4318/booking/{n}?step={n}#NB{n}")
        self.assertEqual(screen["heading"], "Booking")
        reach = [f for f in swarm.aggregate([result], profiles) if f["check_id"] == "RH-01"]
        self.assertEqual(len(reach), 1)
        self.assertEqual((reach[0]["selector_family"], reach[0]["element_count"]), ("header > a.account", 1))
        self.assertEqual(reach[0]["screen"], screen)
        self.assertEqual(reach[0]["screen_key"], screen["key"])

    def test_advisory_warnings_are_summarized_by_rule_and_screen(self):
        profiles, result = self.capture()
        findings = [f for f in swarm.aggregate([result], profiles) if f.get("tier") != "hypothesis"]
        advisory = [f for f in findings if f["severity"] == "P3" and f["check_id"] not in {"SM-06", "CG-02"}]
        self.assertTrue(advisory)
        focus = dict(advisory[0], id="EF-focus", check_id="SM-06")
        listed, summaries = swarm.present(findings + [focus])
        self.assertEqual({f["id"] for f in listed},
                         {f["id"] for f in findings if f["severity"] in ("P0", "P1", "P2")} | {"EF-focus"})
        small = next(s for s in summaries if s["check_id"] == "PT-02")
        members = [f for f in advisory if f["check_id"] == "PT-02"]
        self.assertEqual(small["finding_ids"], [f["id"] for f in members])
        self.assertEqual(small["element_count"], 48)
        self.assertEqual(len(small["observation_ids"]), 48)
        self.assertEqual(small["route"], "http://127.0.0.1/checkout.html")
        self.assertEqual(small["heading"], "Choose")
        self.assertTrue(small["snapshot_ids"])
        self.assertEqual(sum(s["finding_count"] for s in summaries), len(advisory))
        everything, none = swarm.present(findings, "P3")
        self.assertEqual((len(everything), none), (len(findings), []))
        rendered = report.render(findings, profiles, [result])
        self.assertIn("4-1. 자동 참고 경고 요약", rendered)
        self.assertIn(f"| {small['id']} | PT-02 ", rendered)
        for finding in members:
            self.assertNotIn(f"### {finding['id']} ", rendered)

    def test_swarm_cli_list_threshold_keeps_data_and_moves_presentation(self):
        profiles, _ = self.capture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = make_run(root)
            profiles_path = root / "profiles.json"
            profiles_path.write_text(json.dumps({"profiles": profiles}))
            outputs = {}
            for threshold in ("P2", "P3"):
                out = root / f"out-{threshold}"
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    code = cli.main(["swarm", "--runs", str(run_dir), "--profiles", str(profiles_path), "--no-gaze",
                                     "--allow-degraded", "--list-threshold", threshold, "--out", str(out)])
                self.assertEqual(code, cli.EXIT_OK)
                outputs[threshold] = json.loads((out / "findings.json").read_text())
        default, full = outputs["P2"], outputs["P3"]
        self.assertEqual(default["findings"], full["findings"])
        self.assertEqual(full["summaries"], [])
        self.assertEqual(full["listed_finding_ids"], [f["id"] for f in full["findings"] if f.get("tier") != "hypothesis"])
        summarized = {fid for s in default["summaries"] for fid in s["finding_ids"]}
        self.assertTrue(summarized)
        self.assertFalse(summarized & set(default["listed_finding_ids"]))
        self.assertTrue(all(f["severity"] == "P3" for f in default["findings"] if f["id"] in summarized))


if __name__ == "__main__":
    unittest.main()
