<!-- Mode: ergonomics, experimental. Entry point: `SKILL.md`. -->
# Ergonomics mode

Default to a stratified detector run on the real surface: one recorded flow per device/orientation, analyzed across profiles. It needs no subagents. Persona agents, interviews and simulated experience boards are opt-in. Reports can be English or Korean.

For a first offline run, [score the synthetic icon toggle](../../examples/ergonomics/README.md) from the release ZIP. It produces a report and score without capturing a real product.

Run the command examples from a writable work directory outside the installed skill. Set `SKILL_DIR` to the absolute path of the skill folder containing `SKILL.md` (in a source checkout, `skills/remorsearch-ux-qa`). Use the same shell for these steps. Paths like `work/` and `runs/` are relative to your work directory, not the installed skill.

```sh
SKILL_DIR=/absolute/path/to/remorsearch-ux-qa
```

## Phase 0 recap

Use `SKILL.md` Phase 0: scope/build/tasks, devices/orientations, input, supplied data, grants and tools. Choose detector coverage or requested persona-agent behavior. Missing audience research takes the stratified path; explain it. Korean product QA reads `references/persona-qa/kwcag-card.md`; Korean research users/channels open `references/research/korea/overview.md` only when research runs. Before an external page, including a later lead, carry `references/shared/access-card.md` and use research's evidence card. Ask at most one grouped question for necessary missing inputs.

Keep basis visible: **measured** is surface observation against a fixed standard; **model** applies a published model to measured inputs and is inferred; **judgment** is human/LLM inference. Only measured observations from completed runs can be verified. Counts are k/n **simulated-profile coverage**; never real prevalence, preference, discomfort or forecast. Do not role-play pain or seeing difficulty as measurements. The uncalibrated thumb model alone is capped at P2. Model prediction alone cannot reach P0; P0 needs measured safety failure or a declared irreversible action with a computed misfire path. Every P0/P1 needs measured basis or corroborating task trace.

## 1. Frame the scenario

Record actual URL/app/build, task/data, platform/device/orientation and data-mutation risk. Declare roles: primary, destructive, irreversible (only after sandbox confirmation of no confirm/undo), critical_message, error_message, status, hud, game_control, timed, ad_like. Declare transient_text and qte windows. Use the shipped driver init/schema; consult `references/ergonomics/platform-drivers.md` by section for a non-web transport. Repository specification `docs/ergonomic-swarm-spec.md` is not installed with the skill.

```sh
node "$SKILL_DIR/drivers/web/ergo_drive.mjs" devices
node "$SKILL_DIR/drivers/web/ergo_drive.mjs" init --url URL --device DEVICE --task TASK --out sc.json
python3 "$SKILL_DIR/scripts/ergo_qa.py" catalog
```

Use safe steps and authored `success.task_checks` for material values/choices after recovery transitions and at completion; exact payloads, 1-based steps, intentional reset/normalization and `type.redact:true` are in `drivers/web/README.md`. Read-only defaults and separate write grants apply. Production verification/payment, human checks or missing access stop the path. Emulation covers Chromium viewport/DPR/input; real device, grip, keyboard occlusion, safe area and screen reader remain untested.

State/temporal/focus replay contracts: see the driver README.

## 2. Compose profiles

Default stratified coverage:

```sh
python3 "$SKILL_DIR/scripts/ergo_qa.py" profiles --count 16 --seed 7 --devices galaxy-s24,iphone-15 --out work/profiles.json
```

Cover per device right/left one-hand, two-thumb and cradled grips; pointer devices use mouse right/left and keyboard-only. Include condition strata: deutan, presbyopia 60s, mild tremor, walking, low vision, 70s+, small hand; alternate hands. Pointer devices skip walking/small-hand/tremor because only the touch model reads them. Base rates fill remaining slots, never measure this product's audience. Record assumptions, seed, sampled and unfilled facets.

If a completed evidence-backed ergo-audience.v1 was supplied/requested, consult `references/ergonomics/audience-research.md` by section, validate it, then:

```sh
python3 "$SKILL_DIR/scripts/ergo_qa.py" audience-check audience.json
python3 "$SKILL_DIR/scripts/ergo_qa.py" personas --audience audience.json --budget 12 --plan work/persona-plan.md --out work/profiles.json
python3 "$SKILL_DIR/scripts/ergo_qa.py" scenario-stubs --audience audience.json --out scenarios/
```

Research-origin audiences also require the supported gate/bundle/run checks described in `references/research/workflow.md`. Drafts cannot compose; unknown shares stay unknown. Audience composition chooses typical members, weighted one-facet variants and inclusive floors; the plan explains every profile and uncovered facet. Extra conditions follow the audience. A linked narrative dataset needs exact revision/schema/bounded sampling; it has no measured ergonomic attributes. Synthetic/LLM output never supplies audience evidence.

### Select one profile for a recorded run

`--profile` takes one `ergo-profile.v1` object, not the whole profiles document. Choose a profile ID and the device and orientation planned for the capture. The values below match `EP-01` in the stratified example above. For a different profile, set all three and choose a new output path.

```sh
PROFILE_ID=EP-01
DEVICE_ID=galaxy-s24
ORIENTATION=portrait
PROFILE_FILE=work/EP-01.json
python3 - "$PROFILE_ID" "$DEVICE_ID" "$ORIENTATION" "$PROFILE_FILE" <<'PY'
import json
from pathlib import Path
import sys

profile_id, device_id, orientation, output = sys.argv[1:]
profiles = json.loads(Path("work/profiles.json").read_text(encoding="utf-8"))["profiles"]
matches = [p for p in profiles if p["profile_id"] == profile_id]
if len(matches) != 1:
    raise SystemExit("Choose a unique profile_id from work/profiles.json.")
profile = matches[0]
attrs = profile["attributes"]
if profile["schema_version"] != "ergo-profile.v1" or (attrs["device_id"], attrs["orientation"]) != (device_id, orientation):
    raise SystemExit("Choose an ergo-profile.v1 profile for the planned device and orientation.")
with Path(output).open("x", encoding="utf-8") as file:
    json.dump(profile, file, ensure_ascii=False, indent=2)
    file.write("\n")
PY
```

The command refuses to overwrite an existing file. Keep `work/profiles.json` unchanged for analysis and use `PROFILE_FILE` and `PROFILE_ID` in the capture and attachment commands below.

## 3. Record real runs

Use the host browser first or Node.js 22 fallback with installed dependencies:

```sh
node "$SKILL_DIR/drivers/web/ergo_drive.mjs" run --scenario sc.json --device DEVICE --out runs/
python3 "$SKILL_DIR/scripts/ergo_qa.py" analyze --runs runs/ --profiles work/profiles.json --scenario sc.json --cross-profile --out analysis.json
```

One real scripted trace per device/orientation can serve all profiles. Keep screenshots, geometry/colors/timing before/after steps, outcomes and collector versions (default limit 900s). Android uses adb + `android-snapshot`; iOS/desktop/games use platform captures/annotations (`references/ergonomics/platform-drivers.md`). Blocked transports stay untested.

`init` leaves `steps` empty; author transitions or `serve`, then analyze the full task trace (lookup `drivers/web/README.md` section "Task-walk coverage": task × viewport × input + keyboard; unvisited = "not checked"; entry scans alone never prove completion).

Opt-in persona agents use `serve`, `references/ergonomics/persona-agent-protocol.md` and `references/agent-setup.md`; inspect screenshots before touch decisions and record technical/a11y inspection provenance separately. Notes remain judgment. `references/ergonomics/swarm-and-social-layer.md` citations require run/step/observation IDs.

## 4. Analyze, judge and aggregate

```sh
python3 "$SKILL_DIR/scripts/ergo_qa.py" swarm --runs runs/ --profiles work/profiles.json --scenario sc.json --cross-profile --bundle --out report/
python3 "$SKILL_DIR/scripts/validate_bundle.py" report/bundle.json
```

기록된 프로필의 실행은 기존 QA 증거 묶음에 연결할 수 있습니다. 2절에서 만든 단일 프로필 파일과 `PROFILE_ID`를 같은 셸에서 사용해 `R-persona-01`을 기록합니다. 기기만 기록한 위의 `--device` 예시는 분석용 대조에 사용합니다. QA 연결에는 아래처럼 `--profile`을 사용합니다. 제품의 실제 빌드 ID를 넘기면 실행과 모든 캡처에 제공자 지정 정보로 남습니다. 빌드 정보가 없는 결과는 미검증 상태이며 같은 빌드 재현을 주장할 수 없습니다.

정확한 프로필 내용과 모델 리비전을 실행에 고정해야 하는 경우에만 `run` 또는 `serve`에 `--bind-profile`을 추가합니다. 프로필과 일치하는 내장 기기·방향, Python 3.10+가 필요합니다. 이 옵션 없이도 캡처할 수 있지만 프로필 리비전은 검증되지 않습니다.

```sh
node "$SKILL_DIR/drivers/web/ergo_drive.mjs" run --scenario sc.json --profile "$PROFILE_FILE" \
  --build-id "$PRODUCT_BUILD_ID" --out runs/ --run-id R-persona-01
python3 "$SKILL_DIR/scripts/ergo_qa.py" analyze --runs runs/R-persona-01 --profiles work/profiles.json --scenario sc.json --out analysis.json
python3 "$SKILL_DIR/scripts/ergo_qa.py" attach --bundle qa/bundle.json --runs runs/R-persona-01 --profiles work/profiles.json \
  --scenario sc.json --bind "scenario-1=$PROFILE_ID" --receipts-dir receipts/ --out qa/bundle.ergo.json
python3 "$SKILL_DIR/scripts/validate_bundle.py" qa/bundle.ergo.json --artifacts-root receipts/
```

P0/P1은 정확한 `finding_id`의 캡처·텍스트 재검토 기록을 `--second-pass`로 제출합니다. 완료된 값 불일치는 `TI-01` 증거로 연결되며 과업 실패 상태를 유지합니다. 정상 실행도 검사 범위·캡처가 남습니다. 기기·방향·실행 중 캡처 시각과 reflow/focus의 뷰포트·DPR·문맥을 보존합니다. `--out`은 입력·실행 폴더 밖의 새 파일입니다.

Add `--audience audience.json` only for a completed audience. Use the emitted bundle path if this version names it differently. Outputs: findings.json, analyses.json, report.md and an evidence bundle. Segment groups/segments_affected describe triggered profiles, never user shares. Record model IDs and differential conditions (shared by triggered profiles and no untriggered profile). Use `python3 "$SKILL_DIR/scripts/ergo_qa.py" heatmap --help` for reach/gaze review options.

Reach overlays require matching device and orientation. Non-touch input/grip or one-hand tablet-like geometry: exit 2, no image. Matched touch cradle: unchanged image, labeled **no modeled reach penalty**. Neither is scored RH-01/RH-02 coverage or evidence of human reach.

Lookup fired check IDs in `references/ergonomics/human-factors-checks.md`: reach, pointing/Fitts/misfire, gaze, contrast/CVD/visual angle/bright light, choice/reading/latency, game reaction/flash, names/labels/errors/focus/clipping/reflow. Formulas and validity limits are in `ergoqa/params.py`; repository briefs `docs/human-factors/` are not installed. A detector alone cannot decide WCAG size exceptions, irreversible actions, destructive-primary styling, ad-like information, game intent, left-handed options or heuristic fit: record screenshot/step-backed judgment and its limit. ACT examples gate covered checks; a screening result never certifies standards compliance.

## 5. Report, fix and replay

시선·글자 지표·화면 크기 대응은 `references/ergonomics/visual-science.md`의 해당 절을
조회합니다. 과제에 따른 주의, 물리적 기하, 글리프 지표와 실제 내용 손실을 모델의 가정과
구분합니다. RF-02 간격 검사와 RF-03 짧은 창 검사는 기록한 조건에만 적용합니다.
정적 복제 화면은 JavaScript의 실제 크기 변경 동작을 검증하지 못합니다.

Use `references/ergonomics/report-template.md` by section. Decision first, findings ordered by severity/confidence, measured/model/judgment separated, differential conditions and k/n coverage, assumptions and untested platform/device/grip/condition list. Cite source/model limits; benefit claims require measurement. Propose the smallest fix at the deepest confirmed cause (`references/shared/causal-chain.md`). Figma is the design source of truth when present; record version/readback. Proposals follow the project's design rules; flag an existing decoration only with task harm.

Writes need design/test-data/code grants separately. Replay identical scenario/device/profiles after a fix; compare baseline/change/replay and adjacent states. For P0/P1 use persona-qa's fresh capture receipt and second-pass rules. Generated report wording can be English or Korean without changing measured outputs.

## Failure ladder

| Missing/failing | Next step; ask boundary |
| --- | --- |
| Audience | Stratified default with reason/untested facets; do not block screening |
| Browser/platform | Available host transport, then driver; deny/unavailable means real-surface blocker. Ask only for needed access. |
| Source/key | Only requested audience research: card stop, other source family; key set in environment if necessary |
| Verifier | Serial labelled self-pass; unresolved exceptions/flags stay inconclusive. Ask for required human verification. |
| Model input | No guess of geometry/timing; measured or explicitly inferred input, otherwise untested |

## Anti-patterns

| What goes wrong | Why | Fix |
| --- | --- | --- |
| Spawn 16 agents by default | Screening only needs traces/profiles | Detector default; agents opt-in |
| “My thumb hurts” | Synthetic role-play | Computed model, validity cap |
| k/n becomes market percent | Profiles are sampling coverage | State denominator and omissions |
| Thumb model rated P0 | Uncalibrated reach cannot prove harm | P2 cap, measured/task corroboration |
| Vision boxes called measured | Geometry is inferred | Record annotation provenance |

## Done when

Evidence-backed audience or explicit stratified reason; real-surface runs or exact blockers; assumptions/sampling/untested facets recorded; measured/model/judgment separated with model IDs; P0/P1 has measured basis or trace corroboration and fresh receipt/second pass; severity caps hold; counts are simulated coverage; bundle validates when produced; report language, limitations and replay outcome explicit; no unauthorized side effect.
