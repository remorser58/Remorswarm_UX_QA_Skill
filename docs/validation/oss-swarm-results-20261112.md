# 선택적 OSS 페르소나 실행 구현·검증 — 2026-11-12

후속 기록: 아래는 최초 검증 시점의 모델 0회 상태입니다. 같은 날 사용자 승인 Aside 경로로 수행한 [실제 2-persona 모델·도구 실행](aside-live-20261112.md)은 별도 기록이며 이 과거 fixture 결과를 승격하지 않습니다.

## 판정

LangGraph 실행 계층과 fixture 검증은 구현했습니다. **실제 모델을 사용하는 두 페르소나 스웜의 완료조건은 미충족입니다.** 최초 검증 당시 일반 Web GPT Agent의 agents/status와 후속 tools_search는 `McpServerError: Connection failed`를 반환했습니다. 실제 페르소나 모델 호출은 0회입니다. 다른 모델/API나 권한 확대를 대체 경로로 사용하지 않았습니다.

후속 [Secure transport 진단](oss-swarm-transport-diagnosis-20261112.md)은 정확한 daemon 프로필이 정상이고 browser transport도 켜져 있음을 확인했습니다. Secure에는 직접 `work`가 있으며 `agents`는 현재 노출되지 않습니다. nested tools_search의 부재만으로 lifecycle 기능 부재를 단정할 수 없습니다. 기존 work의 `ready`는 약 69시간 전 페이지 관측을 사용했고, Remorsearch의 `host_ready`는 false입니다. 이 진단은 실제 모델 실행이나 transport 구현 완료를 뜻하지 않습니다.

실제 StateGraph/AsyncSqliteSaver 호출, 독립 컨텍스트, 도구 왕복, 첫 판단 고정, 근거 검사, 보고서 생성은 실행했습니다. 아래 브라우저 진단의 판단과 검증 함수는 **작성된 fixture**입니다. 이를 자율 AI 판단, 실사용자 조사, Peekly QA 또는 제품 개선 완료로 해석하면 안 됩니다.

[기계 판독 기록](oss-swarm-results-20261112.json)에는 컨텍스트·페르소나·첫 판단·요청·증거 해시, 시간선, 정확한 gate 결과와 남은 공백을 보관합니다.

## 작업 범위와 구현

출발점은 `7359fb6c8c770601598d431b92d350bda20096d9`, 브랜치는 `rem/oss-swarm-20261112`입니다. 사용자가 수정한 승인 경로 `/Users/r3m0r5e/CodeProjects/remorsearch-ux-qa-resume/.ux-loop/oss-swarm-20261112/worktree`를 사용했습니다. 정확한 브랜치·HEAD·clean 상태를 확인한 뒤 원래 프로젝트에서 공식 `git worktree move`로 이번에 만든 형제 worktree만 옮겼고, 이후 승인된 read를 확인했습니다.

- `uxpersonas/agent_run.py`: 실제 LangGraph model→tool→model 반복, 페르소나별 SQLite checkpoint, 상호 답변 없는 첫 판단과 후속 검증. 기존 Library/claim/receipt/PNG/PRD/연구 게이트를 호출합니다.
- `uxpersonas/agent_entry.py`: 호스트가 검토한 대상·목표·빌드와 현재 저장된 2–8개 페르소나를 연결합니다. 동일 목표/빌드의 중복 실행 예약을 막습니다. 사용자에게 JSON·lease·모델 선택을 요구하지 않습니다. PRD 인용은 탐색 기준이며, 호스트의 의미 적합성 검토가 필요합니다.
- `scripts/ux_agents.py`: 무설치 진단과 현재 근거에 대한 보고서 재조회. 선택적 의존성은 지연 import합니다.
- `examples/agents/`: 작성된 결정 함수와 합성 2×2 PNG 진단, 실제 소유 Chromium 진단을 분리했습니다.
- 시간·턴·동시 호출 제한, 취소, 정확한 operation/context/request hash, dispatch 전 durable intent, 늦은 응답 거부, receipt 응답 손실 재조회, 불명확한 효과 격리를 적용했습니다. 재시작 시 모델/도구를 자동 반복하지 않습니다.

`CallbackHost`는 검토된 호스트 코드를 연결하는 인터페이스입니다. Web GPT Agent나 AGY의 동작하는 transport를 구현했다고 주장하지 않습니다. 호스트가 실제 격리·도구 권한·동일 연구 호스트의 직렬 접근·종료를 보장해야 합니다. OS/network sandbox가 아닙니다.

기존 `swarm.py`, `browser_run.py`, `journey_bridge.mjs`, `session.mjs`, `validate.mjs`, `check_release.py`와 기존 관련 테스트는 수정하지 않았습니다. 새 브라우저 진단은 기존 bridge의 transport 제한 함수를 import하므로 향후 통합 시 해당 계약을 확인해야 합니다. 공유 문서 PRD/SKILL/release/notices에는 작은 연결 변경이 있습니다. 다른 worktree를 변경하지 않았고, Peekly 대화·작업에는 접근하지 않았습니다.

## OSS 선택과 라이선스

[OpenAI Swarm](https://github.com/openai/swarm)은 실험적 프로젝트이며 production에는 Agents SDK를 권합니다. [Agents SDK](https://github.com/openai/openai-agents-python)도 검토했으나 이번에 import하지 않았습니다.

[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview)는 특정 모델 연결 없이 그래프 실행과 checkpoint를 기존 승인 경계에 붙일 수 있어 선택했습니다. `langgraph==1.2.20`, `langgraph-checkpoint-sqlite==3.1.3`을 공식 PyPI에서 전용 환경에 설치했고, 실제 compile/ainvoke/SQLite를 실행했습니다. 두 의존성은 MIT이며 notices와 선택적 requirements에 반영했습니다. upstream 코드는 vendoring하지 않았습니다. 모델 API/자격증명 조회/원격 tracing을 구성하지 않았고 graph 실행에서 tracing을 끕니다.

[Interrupt](https://docs.langchain.com/oss/python/langgraph/interrupts) 후 node가 다시 실행될 수 있으므로 checkpoint를 도구 재실행 권한으로 취급하지 않았습니다. 이번 구현은 저장 receipt의 확인·유효한 원래 lease 안의 admission만 복구합니다.

## 실제 브라우저 근거

두 저장 페르소나는 같은 PRD에 근거한 서로 다른 합성 profile revision 1입니다. profile hash는 서로 다릅니다. 공개 사용자 근거로 검증된 인물은 아닙니다.

| 항목 | 최종 원본 진단 |
| --- | --- |
| 실행 모드 | authored fixture + 실제 owned headless Chromium |
| 저장 페르소나 / 독립 컨텍스트 | 2 / 2 |
| 판단 콜백 / 실제 모델 호출 | 12 / **0** |
| 실제 브라우저 도구 호출 / PNG | 10 / 10 |
| 동시 host callback 최대치 | 2; 모델 서버의 병렬 실행을 뜻하지 않음 |
| 첫 판단 | 2개 고정·해시 후 각자 검증 |
| 결과 | 정상 1 passed, 결함 1 failed |
| 종료 / 재조회 | 두 context 종료 확인; 재조회 때 dispatch 0회 |
| HTML SHA-256 | `dca43f5dc4505f34897eac9dbe3425f7bfe174d8aad9e5140e91b831e90d372d` |

오류를 거절한 직후 정상 경로는 `Owned draft`를 유지했고 결함 경로는 입력을 비웠습니다. 두 경로 모두 나중에 수정한 값을 저장했지만 결함 경로의 앞선 실패는 그대로 남았습니다. 동일 recovery 관측은 중복으로, 입력 보존 결과의 차이는 상충으로 표시하며 독립 사용자 투표로 집계하지 않습니다.

- [정상 오류 경로 PNG](oss-swarm-20261112/control-rejection.png), [원본 관측 JSON](oss-swarm-20261112/control-observation.json)
- [입력 손실 경로 PNG](oss-swarm-20261112/defect-rejection.png), [원본 관측 JSON](oss-swarm-20261112/defect-observation.json)
- [후속 복구 PNG](oss-swarm-20261112/recovered-note.png), [원본 관측 JSON](oss-swarm-20261112/recovery-observation.json)

위 여섯 파일은 최종 진단에서 바이트를 그대로 복사한 증거입니다. 전체 10 PNG·10 관측·SQLite·journal·report·Library는 이 worktree의 `.ux-loop/agent-browser-final/`에 남아 있습니다. 사용자 Chrome, 화면, 키보드를 사용하지 않았습니다.

## 검증 결과와 Mac 측정

| 명령/검사 | 결과 | elapsed | maxRSS bytes |
| --- | --- | ---: | ---: |
| 새 agent 회귀 suite | 23 tests, OK, skip 0 | 6.54 s | 104,431,616 |
| 강화된 회귀 포함 최종 전체 suite | 1,440 tests, OK, skipped 1 | 195.31 s | 227,409,920 |
| 원본 실제 브라우저 진단 | exit 0, control pass / defect fail | 12.62 s | 109,707,264 |
| 전체 release gate | exit 0, 21 checks passed, ready true | 502.22 s | 235,454,464 |
| 추출 패키지의 agent 직렬 진단 | exit 0, 동시 호출 최대 1 | 1.18 s | 98,533,376 |
| 추출 패키지의 실제 브라우저 진단 | exit 0, control pass / defect fail | 12.37 s | 109,199,360 |

`/usr/bin/time -l`의 실제 Mac 값입니다. maxRSS는 해당 도구가 보고한 수치이며 동시에 실행한 모든 Chromium 하위 프로세스 메모리의 합계 측정이 아닙니다. 실제 모델 지연·UX 성과나 통제된 성능 벤치마크를 측정한 것은 아닙니다.

전체 gate 안에서 Python은 1,440 tests / OK (skipped=1), Chromium은 559 passed / 0 failed, browser bridge는 7 passed였습니다. Python의 한 skip은 별도 실제 캡처 입력이 필요한 painted-state 사례입니다. 브라우저 로그에는 공유 browser-server handshake와 Python captured-font 분석이 해당 선택적 환경변수 부재로 제외돼 있습니다. ZIP/추출/참조 본문/기존 research·loop smoke/local·research·browser journey/실행 후 무결성/현재 package match/검증 중 source 안정성이 모두 통과했습니다. `ready: true`는 이 로컬 패키지 gate의 결과이며 제품이나 실제 모델 스웜의 완료 판정이 아닙니다.

gate 후 새 agent 회귀 두 항목만 강화했습니다. 하나는 owned 파일의 효과를 fsync한 직후 프로세스가 exit 73으로 끝난 뒤 재시작했을 때, dispatch 0회·효과 1회·mtime 보존·attempt 1·격리가 유지되는지 확인합니다. 다른 하나는 취소를 무시하고 돌아온 늦은 tool 응답이 admission되지 않는지 확인합니다. 강화된 23개 시험과 최종 전체 1,440개 suite가 모두 통과했습니다. 실행 코드와 패키지 바이트는 변하지 않았으며, 현재 package manifest가 검증 후보와 같고 복사한 증거 6개가 원본과 동일함을 다시 확인했습니다. 최종 suite의 unittest 내부 시간은 194.625초, 프로세스 elapsed는 195.31초입니다.

선택적 패키지가 없는 기본 Python의 doctor는 예상 exit 2와 정확한 누락 목록을 반환했습니다. 같은 기본 Python으로 원본 및 추출 패키지의 최종 브라우저 report 재조회는 exit 0이었고, 추가 브라우저 실행 뒤 추출 패키지 무결성도 exit 0이었습니다. 설치 없이 쓰는 기존 경로를 유지했습니다. 실제 설치한 선택적 환경의 전이 의존성 버전 42개는 기계 판독 기록에 보관했습니다.

초기 브라우저 진단 두 번은 실패했습니다. SHA-256 metadata를 개인정보 자유 텍스트로 검사한 오류와, browser close 뒤 stdin이 열려 프로세스 종료 확인이 실패한 문제를 고쳤습니다. 원본 실패 기록은 `.ux-loop/agent-browser-initial/`, `.ux-loop/agent-browser-second/`에 보존했습니다. 최초 reading-budget 초과 14 bytes도 상한을 바꾸지 않고 routing 문구를 줄여 해결했습니다.

## 실제 실행 명령

아래는 실행에 사용한 경로입니다. 재실행할 때 결과 디렉터리는 반드시 새 이름을 사용합니다. 이미 존재하는 결과를 덮어쓰지 않습니다. 이 절은 유지보수자 재현용이며 일반 사용자 입력 계약은 대상과 목표입니다.

~~~sh
R=/Users/r3m0r5e/CodeProjects/remorsearch-ux-qa-resume/.ux-loop/oss-swarm-20261112/worktree
B=/Users/r3m0r5e/CodeProjects/remorsearch-ux-qa-resume/.ux-loop/web-pro-browser-journey-20261112/worktree/.ux-loop/browser-runtime
P="$R/.ux-loop/agent-env/bin/python"
cd "$R"
env PYTHONDONTWRITEBYTECODE=1 REMORSEARCH_REQUIRE_AGENT_RUNTIME=1 \
  /usr/bin/time -l "$P" -m unittest discover -s tests -p test_agent_execution.py -v
env PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/time -l "$P" skills/remorsearch-ux-qa/examples/agents/browser_fixture.py \
  --out .ux-loop/agent-browser-final \
  --node "$B/node-v22.16.0-darwin-arm64/bin/node" \
  --playwright "$B/node_modules/playwright" --browsers "$B/chromium"
env PYTHONDONTWRITEBYTECODE=1 REMORSEARCH_REQUIRE_AGENT_RUNTIME=1 \
  PATH="$B/node-v22.16.0-darwin-arm64/bin:$PATH" PLAYWRIGHT_BROWSERS_PATH="$B/chromium" \
  /usr/bin/time -l "$P" scripts/check_release.py --output .ux-loop/validation/release-final
env PYTHONDONTWRITEBYTECODE=1 REMORSEARCH_REQUIRE_AGENT_RUNTIME=1 \
  /usr/bin/time -l "$P" -m unittest discover -s tests -p 'test_*.py'
python3 skills/remorsearch-ux-qa/scripts/ux_agents.py doctor --format json
python3 skills/remorsearch-ux-qa/scripts/ux_agents.py report \
  --library .ux-loop/agent-browser-final/library --run .ux-loop/agent-browser-final/run
~~~

추출 검증은 `.ux-loop/validation/`을 cwd로 쓰고 `PYTHONPATH=''`를 지정했습니다. `release-final/extracted/remorsearch-ux-qa/examples/agents/fixture.py --serial`과 같은 폴더의 `browser_fixture.py`를 실행했습니다. 기존 Node 22.16.0 / Playwright 1.56.1 / Chromium을 읽기 전용으로 재사용했고 browser/build runtime을 복사하지 않았습니다. 기존 release checker의 작은 추출 패키지와 npm dependency 준비 동작은 그대로 사용했습니다.

## 남은 완료조건

1. 승인된 실제 모델 호스트의 확인된 transport가 필요합니다. 현재 callback 계약만 존재하며 Web GPT Agent/AGY 지원 완료가 아닙니다.
2. 두 저장 페르소나가 독립 실제 모델 컨텍스트에서 각자의 관측으로 도구를 선택하고 첫 판단·PNG·보고서까지 끝낸 실행은 아직 없습니다.
3. URL만 받은 PRD→허용된 실제 공개 조사→지속 persona→자율 모델 QA의 전체 live acceptance를 실행하지 않았습니다. 목표 entry는 호스트의 검토·준비를 전제로 합니다.
4. 중단된 모델 대화의 자동 이어가기, 실제 원격 도구의 취소·중복 방지, live-model 성능은 이 fixture로 검증되지 않습니다.
5. 공개 근거의 진위, 실사용자 대표성·효과, Peekly 결과, 제품 준비도는 주장하지 않습니다.
