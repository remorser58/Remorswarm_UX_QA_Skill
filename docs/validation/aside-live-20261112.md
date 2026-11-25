# Aside 소유 Pro 컨텍스트의 실제 2-persona 실행 — 2026-11-12

## 판정과 범위

**최종 소스에서 서로 다른 저장 페르소나 두 개가 독립된 새 Pro 대화에서 실제 모델 → 도구 → 모델 → 첫 판단 → review를 완료했습니다.** 최종 실행은 `.ux-loop/aside-live-model-20261112-09`이며 exit 0입니다. 실제 persona 모델 판단 12회, 실제 owned Chromium 도구 10회, 봉인된 첫 판단 2개, 실제 review 2회입니다. 별도의 transport probe 2회는 persona 실행 수에 포함하지 않았습니다. authored model decision은 0회입니다.

정상 대조는 passed, 알려진 입력 손실 경로는 failed입니다. 수정 입력을 저장하는 recovery는 양쪽 모두 passed지만 앞선 실패를 지우지 않았습니다. 두 worker의 owned page 제거·SSH exit 0·Chromium 종료를 확인했고, 완료 결과를 다시 읽을 때 추가 dispatch는 0회였습니다.

이것은 **모델 transport와 실제 행동 실행 경로의 수용 검증**입니다. 시험 HTML·도구 목록·정상/결함 조건과 PRD 가설은 작성된 진단 입력입니다. 모델은 각자의 입력 문구, 다음 도구, 종료 시점과 판단을 선택했습니다. 임의 제품 URL을 탐색하는 범용 도구, 실제 공개 조사로 뒷받침한 페르소나, 실사용자 효과나 Peekly QA를 검증한 것은 아닙니다. 전체 제품의 `product_ready`와 `actual_user_evidence`는 false입니다.

- [실제 실행 원본 요약](aside-live-20261112/diagnostic.json)
- [모델 요청·실제 응답·nonce·해시 16묶음](aside-live-20261112/model-transcripts.json)
- [저장 profile·컨텍스트·봉인 판단·review·종료 영수증](aside-live-20261112/contexts.json)
- [통합 보고서](aside-live-20261112/report.md), [기계 판독 보고서](aside-live-20261112/report.json)
- [증거 export 무결성 검사](aside-live-20261112/verification.json)
- [이전 시도와 실제 실패 기록](aside-live-20261112/prior-attempts.json)

## 승인된 경로와 원인 구분

작업 시작 HEAD는 `d25a7e857190f52d805f7872ad2253b6261be7ed`, 브랜치는 `rem/oss-swarm-20261112`입니다. 승인된 기존 worktree 안에서만 구현·검증했습니다.

`/Users/r3m0r5e/CodeProjects/remorsearch-ux-qa-resume/.ux-loop/oss-swarm-20261112/worktree`

이전 [Secure 진단](oss-swarm-transport-diagnosis-20261112.md)은 daemon/MCP가 살아 있어도 Remorsearch 모델 callback이 연결되지 않았고, 직접 agents 도구가 노출되지 않았음을 기록합니다. 그 진단은 당시 사실로 보존합니다. 오래된 일반 연결의 세부 장애 원인을 이번 실행으로 소급 확정하지 않습니다. agents는 별도 숨겨진 endpoint를 호출해 얻는 기능이 아니며, 기존 managed work의 오래된 ready도 실행 준비 증거가 아닙니다.

이번에는 사용자가 추가로 지정한 **기존 Secure MCP → MacBook SSH alias → Mac mini Aside 공식 CLI → 새 소유 배경 페이지** 경로를 연결했습니다. Secure agents 도구를 되살린 것이 아니라, Remorsearch의 검토된 host callback에 실제 동작하는 별도 승인 transport를 구현했습니다. 설정 변경이나 새 외부 권한은 없었습니다. `multiAgent.enabled=false,maxWorkers=1`을 바꾸지 않았고, Aside의 독립 REPL 세션 두 개가 각자 소유한 새 대화를 사용했습니다.

실행 전에 설치된 CLI의 `guide`, `guide repl`, `skills list`, `skills show aside`, 도움말과 세션 제어 인터페이스를 읽었습니다. 확인한 CLI 버전은 **1.26.1107.24**, Aside skill은 **version 4**입니다. 지원되는 `openTab`·`closeTab`·`snapshot`·locator fill/click과 이미 관측한 정확한 DOM의 제한된 읽기만 사용했습니다. `aside exec`, 비공식 HTTP/API, 내부 React 상태, cookie/token 접근은 사용하지 않았습니다.

Aside 서비스 계정 17과 Profile0 안의 ChatGPT 로그인 18 Pro는 사용자 제공 식별 정보이며 서로 다릅니다. 실행에서는 각 새 페이지의 표시 모델 **Pro**, 임시 채팅 및 비개인화 상태를 관측했습니다. provider 내부 모델 버전·계정 entitlement를 별도 API로 인증한 것은 아닙니다.

각 REPL은 `pageBound=false,ownedTabs=0`에서 출발했습니다. 공식 `openTab`으로 만든 한 페이지만 소유했고, 기존 홈페이지·미전송 초안·이 대화·Peekly 대화에 attach/send하지 않았습니다. 각 새 대화에서 짧은 nonce probe를 먼저 왕복한 뒤 persona 실행을 시작했습니다.

## 실제 두 컨텍스트

| 항목 | Cautious first-time note writer | Returning note writer after interruption |
| --- | --- | --- |
| 저장 persona / revision | `PER-CAUTIOUS` / 1 | `PER-RETURN` / 1 |
| Aside 새 세션 | `V0oarz2FXziBjZK6` | `tHhYaMfO2gUroCXs` |
| context | `ctx-749e1a6463d03e483bd7a3a3555378ba42dc5be9` | `ctx-c42496c7418a0dee18f318e4da876517b16337f1` |
| persona 근거 | 저장된 PRD 합성 가설 | 저장된 PRD 합성 가설 |
| 행동 성향 | 익숙하지 않은 상태부터 확인하고 거절 뒤 입력 보존을 확인 | 중단 뒤 남은 작업을 확인하고 손실 시 필요한 만큼만 복구 |
| 실제 선택 | inspect → enter → reject → enter → save → final | inspect → enter → reject → enter → save → final |
| 판정 / recovery | passed / passed | failed / passed |
| 종료 | page closed, SSH 0, browser stopped | page closed, SSH 0, browser stopped |

Profile SHA-256:

- CAUTIOUS: `ac2cbf8dcf5ba59ffa142afdc81b474d715815f0175f5904a2b1143b8af63c1e`
- RETURN: `febd7c7bb4237fb7bc23a632b7fac191e2b405a2bafac19292ceab71ef421b44`

봉인된 첫 판단 SHA-256:

- CAUTIOUS: `fb1ef9519e4bcaa61f91ebb19409bb06be64b64286e7c86cadd3eed4b5a8729e`
- RETURN: `538bf0a5e1c42f4cb8cc14508c2241a7987b78c971480ef48f68eb6c618c9fa0`

각 persona는 Library에 저장된 profile과 현재 revision/PRD binding을 읽었습니다. 서로의 답변은 prompt에 제공하지 않았고, export 검사는 상대 persona ID와 상대 첫 판단의 reasoning이 각 prompt에 없는지도 확인했습니다. 첫 판단 종료 시각은 각 review 시작 시각보다 빠릅니다. review는 **같은 persona의 근거 재검토**이며 독립 제3자의 투표가 아닙니다.

두 모델이 같은 도구 순서를 선택한 것은 고정 실행 스크립트의 증거가 아닙니다. 실제 요청은 도구 설명과 과업/자기 관측을 제공했고, 각 응답의 도구명·입력·reason을 검증한 뒤 실제로 실행했습니다. 다만 작은 도구 집합과 알려진 진단 과업에서 얻은 이 결과가 광범위한 자율 탐색 능력을 입증하지는 않습니다.

## 결함과 재검토 근거

정상 경로는 모델이 입력한 `Owned draft before rejection.`을 거절 뒤에도 그대로 유지했습니다. 결함 경로는 `Owned returning draft after interruption.`을 빈 문자열로 바꿨습니다. 실제 DOM의 before/after 값, native checkpoint, PNG가 같은 결과를 가리킵니다.

| 관측 | 실제 값 | 증거 |
| --- | --- | --- |
| 정상 거절 | before와 note 동일, retained=true | [PNG](aside-live-20261112/browser/T-CAUTIOUS/actual-browser-3.png), [원본 관측](aside-live-20261112/browser/T-CAUTIOUS/agent-observation-3.json) |
| 결함 거절 | note 빈 문자열, retained=false | [PNG](aside-live-20261112/browser/T-RETURN/actual-browser-3.png), [원본 관측](aside-live-20261112/browser/T-RETURN/agent-observation-3.json) |
| 정상 recovery | `Owned corrected note after rejection.` 정확히 저장 | [PNG](aside-live-20261112/browser/T-CAUTIOUS/actual-browser-5.png), [원본 관측](aside-live-20261112/browser/T-CAUTIOUS/agent-observation-5.json) |
| 결함 뒤 recovery | `Owned returning draft after interruption. Corrected after rejection.` 정확히 저장 | [PNG](aside-live-20261112/browser/T-RETURN/actual-browser-5.png), [원본 관측](aside-live-20261112/browser/T-RETURN/agent-observation-5.json) |

RETURN의 실제 review는 recovery 성공과 원래 retention 실패를 각각 유지합니다. 여기서 recovery는 제품을 수정했다는 뜻이 아닙니다. 이번 transport 작업은 진단 HTML의 의도된 결함을 고치지 않았고, 수정된 제품 빌드의 효과를 재검증했다고 주장하지 않습니다.

최종 export는 **30개 파일, 888,034바이트, 실제 제품 PNG 10개**입니다. PNG는 CRC와 전체 픽셀 decode, 해시·경로·receipt binding을 검증했습니다. 모델에는 자기 DOM 관측과 PNG 해시가 전달됐으며 **PNG 픽셀 자체는 업로드되지 않았습니다**. 따라서 행동/상태 QA이며 모델의 시각적 평가를 입증하지 않습니다.

시도 08의 Pro 페이지 캡처를 사람이 확인하는 과정에서 요청한 대화 clip에 계정 사이드바 일부가 포함됨을 발견했습니다. 해당 export 전체를 미추적 로컬 보관 위치로 이동하고 provider screenshot 기능을 제거했습니다. 최종 09는 provider PNG를 아예 생성하지 않았고 제품 PNG만 내보냅니다. 앞선 원본은 수정·가림 처리하지 않았으며 커밋에 포함하지 않습니다. 실제 응답과 송수신 영수증은 그대로 검증 가능한 증거입니다.

## 실제 병렬성과 측정

| 항목 | 최종 09 실측 |
| --- | ---: |
| 저장 persona / 독립 모델 context | 2 / 2 |
| 실제 persona model / tool / review | 12 / 10 / 2 |
| 별도 transport probe | 2 |
| authored model decisions | 0 |
| 최대 동시 model callback / tool callback / review callback | 2 / 2 / 2 |
| 교차 context Send→응답 구간 겹침 | 8개, 약 1.05–8.43초 |
| 전체 진단 elapsed | 86.131089875초 |
| MacBook coordinator maxRSS | 102,563,840바이트 |
| coordinator user / system CPU | 12.989804 / 0.990923초 |
| 판정 | passed 1, failed 1, inconclusive 0, blocked 0 |
| 완료 결과 재조회 | report 동일, 추가 dispatch 0 |

동시 callback뿐 아니라 실제 각 대화의 Send→응답 시각도 보존했습니다. 최종 09는 두 owned Chromium 도구 callback도 겹쳤습니다. 이전 08은 model/review는 겹쳤지만 tool peak는 1이었습니다. 이를 혼합해 모든 시도에서 병렬 브라우저 동작이 있었다고 쓰지 않습니다. provider 내부 추론 연산/GPU 병렬성은 관측할 수 없습니다.

elapsed는 새 페이지 생성 후 진단 초기화부터 보고/재조회까지의 coordinator monotonic 시간입니다. maxRSS는 macOS `resource.getrusage(RUSAGE_SELF)`의 바이트입니다. SSH 준비 전체, 원격 Pro 메모리 또는 모든 Chromium 자식 프로세스 메모리의 합계가 아닙니다. 이 단일 진단은 통제된 성능 벤치마크나 실사용자 시간 절감 측정이 아닙니다.

한도는 parallel=2, turns=12, call_seconds=180, task_seconds=1500, close_seconds=15, 원래 lease=1800초, max_attempts=1입니다. daemon worker 설정과 별개인 host 실행 한도이며 OS/network sandbox가 아닙니다.

## 구현과 회귀 경계

`aside_cli.py`는 승인된 SSH alias/profile로 공식 REPL을 열고 PTY echo와 실제 단독 JSON 응답을 구분합니다. RPC마다 durable intent와 nonce를 저장합니다. EOF·timeout·cancel·불확실한 송신 후 자동 재전송하지 않고 해당 context를 격리합니다. 기존 journal 또는 page를 재사용하지 않습니다. 종료는 소유 page 제거와 SSH 종료를 함께 확인합니다.

`aside_chatgpt.py`는 관측한 한국어 UI에 고정된 adapter입니다. 처음부터 Pro가 아니면 멈추며 모델을 바꾸지 않습니다. 임시·비개인화 상태, 빈 composer, 실제 visible editor의 정확한 입력값, 현재 Send ref, 새 assistant ID와 operation nonce를 확인합니다. 16 KiB snapshot 한도에 긴 prompt가 잘리지 않도록 관측한 Send만 좁혀 snapshot하고 전체 입력은 정확한 DOM에서 비교합니다. hidden duplicate editor와 오래된 assistant remount는 새 결과로 admit하지 않습니다.

도구는 별도 `OwnedNoteTools`의 실제 headless Chromium에서 실행됩니다. 허용 도구/argument 외의 동작을 모델이 직접 수행할 수 없습니다. 제품 텍스트는 untrusted data로 전달하며 PRD·profile·build·request·evidence binding과 기존 연구/권한/retention gate를 보존합니다. host callback의 검토된 tool code를 OS 보안 격리라고 부르지 않습니다.

실제 OSS는 기존 선택적 `LangGraph StateGraph`·`AsyncSqliteSaver`를 import/compile/ainvoke하는 경로입니다. [OpenAI Swarm](https://github.com/openai/swarm)의 production 대안 안내와 [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview)를 검토한 기존 선택을 유지합니다. `langgraph==1.2.20`, `langgraph-checkpoint-sqlite==3.1.3`은 MIT이며 notice에 기록돼 있습니다. Aside는 별도 설치·별도 라이선스 도구이며 그 코드나 문서를 번들하지 않았습니다. Agents SDK·OASIS·AGY를 실제 통합했다고 표기하지 않습니다.

기존 `agent_run.py`에서는 완료된 실제 model callback이 겹쳤을 때만 실제 model 병렬성을 인정하고, review count를 분리했습니다. 모델/review 중단 시에도 이미 검증한 native failure·PNG·로그를 보존하며 전체 결과는 inconclusive로 남깁니다. 완료 기록 재조회와 재시작은 불확실한 효과의 재실행 권한이 아닙니다.

회귀는 EOF/취소/timeout, 늦은 응답, stale ID/hash, 중복 결과, 바뀐 profile binding, 부분 tool failure, 종료 불확실성, 미전송 초안, non-Pro 상태, loading UI, 프로세스가 fsync된 효과 직후 exit 73으로 중단된 뒤 재시작해도 효과 1회/dispatch 0회를 유지하는 경우를 다룹니다. 이 시험은 protocol simulation이며 실제 모델 호출 수에 넣지 않습니다.

사용자 입력 entry는 기존 `agent_entry.run_goal`입니다. host가 `open_owned_host`로 승인된 transport와 검토된 도구를 제공하며 사용자는 대상과 목표를 줍니다. alias/profile/runtime 경로는 유지보수자 또는 host 설정입니다. 일반 사용자에게 JSON 작성이나 모델 수동 선택을 강요하지 않습니다. 다만 이 entry를 모든 외부 제품에 적용하는 완성된 범용 탐색 adapter는 아직 없습니다.

## 이전 시도 보존

실패를 성공 데이터로 다시 포장하지 않았습니다. 표의 모델 수는 persona decision이며 probe와 review는 별도입니다.

| 시도 | 모델 / tool / accepted review | 결과와 원인 |
| --- | --- | --- |
| 최초 빈 REPL helper | 0 / 0 / 0 | non-TTY EOF. 정확한 두 CLI session stop은 exit 0이나 독립 closeTab 영수증은 없어 page 제거를 확정하지 못함 |
| 01 | 6 / 6 / 0 | 긴 대화의 composer snapshot이 누락. 첫 판단 없음 |
| 02 | 6 / 6 / 0 | fill 뒤 composer snapshot 누락. 초기 stopped=false 보존; 이후 exact owned close와 SSH 종료 확인 |
| 미전송 DOM probe | 0 / 0 / 0 | 실제 DOM 조상 깊이가 기존 guard보다 큼. 모델 Send 없음 |
| 03 | 0 / 0 / 0 | visible/hidden editor 중복을 ambiguous로 거절 |
| 04 | 0 / 0 / 0 | 새 페이지 loading 상태에서 Pro preflight 미준비; graph 시작 전 중단 |
| 05 | 2 / 0 / 0 | external host tool과 ChatGPT native tool의 구분이 prompt에 불명확해 not_run. review 송신 뒤 오래된 decoder로 불확실해짐 |
| 06 | 10 / 10 / 0 | 긴 prompt와 제목이 16 KiB snapshot 한도를 소비; 마지막 prompt는 전송되지 않음 |
| 07 | 12 / 10 / 0 | 실제 첫 판단 2개, review 응답도 왔으나 response_to/result envelope 없음. strict decoder가 거절; completion=false |
| 08 | 12 / 10 / 2 | 모델/도구 완료. 후속 PNG 검토에서 provider sidebar 포함 발견, export 제외 후 screenshot 기능 제거 |
| **09** | **12 / 10 / 2** | **최종 소스 완료, provider screenshot 0, 두 context 종료 확인** |

이전 05와 07처럼 reply correlation을 끝까지 확인하지 못한 경우 page/SSH 종료만으로 provider 서버의 generation cancel을 증명하지 않습니다. 07의 stopped=false 및 05 당시 기록의 한계를 유지합니다. 최초 빈 helper 역시 page 제거 증거가 부족합니다. 이 세션들을 다시 attach하거나 재전송하지 않았습니다. 이후 수정 검증은 별도의 새 소유 페이지와 별도의 synthetic local 데이터에서만 했습니다.

08 elapsed 88.5791735초 / coordinator maxRSS 105,185,280바이트와 최종 09의 측정은 각각 보존합니다. 이전 실패의 세부 raw trace와 후보 응답은 `prior-attempts.json`에 있으며 로컬 원본 디렉터리도 남아 있습니다. 실패 횟수나 불확실성을 숨기려고 원본 verdict를 바꾸지 않았습니다.

## 명령과 독립 검사

최종 실제 명령은 승인된 worktree에서 다음과 같습니다. 아래 profile은 사용자가 지정한 Aside profile 식별자이며 비밀 인증 토큰이 아닙니다.

```sh
PYTHONDONTWRITEBYTECODE=1 .ux-loop/agent-env/bin/python -u \
  skills/remorsearch-ux-qa/examples/agents/run_aside_live.py \
  --ssh-alias m4mini-work \
  --aside-profile u0:19e8a5aa-12ce-49c2-b3a1-94898fd6641d \
  --out .ux-loop/aside-live-model-20261112-09 \
  --node /Users/r3m0r5e/CodeProjects/remorsearch-ux-qa-resume/.ux-loop/web-pro-browser-journey-20261112/worktree/.ux-loop/browser-runtime/node-v22.16.0-darwin-arm64/bin/node \
  --playwright /Users/r3m0r5e/CodeProjects/remorsearch-ux-qa-resume/.ux-loop/web-pro-browser-journey-20261112/worktree/.ux-loop/browser-runtime/node_modules/playwright \
  --browsers /Users/r3m0r5e/CodeProjects/remorsearch-ux-qa-resume/.ux-loop/web-pro-browser-journey-20261112/worktree/.ux-loop/browser-runtime/chromium \
  --reviewed-owned-route
```

기존 Node 22.16.0 / Playwright 1.56.1 / Chromium과 선택적 Python 환경을 재사용했습니다. 이번 변경을 위해 의존성을 새로 설치하거나 browser/build tree를 중복 복사하지 않았습니다. release checker의 작은 준비된 node_modules 복사는 그 기존 격리 검증 절차입니다.

`ux_agents.py doctor --format json`은 선택적 환경에서 exit 0 / runtime_ready=true, 기본 Python에서는 예상 exit 2 / 누락 LangGraph 두 패키지를 반환했습니다. host를 전달하지 않는 이 CLI doctor의 host_ready=false는 정상이며 실제 transport 실행 결과와 구분합니다. 기본 stdlib 경로는 유지됩니다.

최종 live 실행의 [8개 소스 해시](aside-live-20261112/source-manifest.json)는 실행 전후 같았고 export 시 현재 소스와도 일치했습니다. 원본 runtime state는 lease를 포함하므로 배포하지 않고 digest만 보존합니다. export는 credential/lease 필드를 제외하고 실제 reply의 nonce·prompt/hash·candidate/hash·first judgment/hash·각 PNG·종료 영수증을 별도로 검증했습니다.

## 최종 전체 검증 결과

[기계 판독 release·relocation 기록](aside-release-20261112.json)에 두 gate의 원래 verdict, 전체 check 목록, 각 로그 해시, 실제 명령, time -l 원문과 추가 진단을 보관합니다.

| 검사 | 실제 결과 | elapsed | maxRSS bytes |
| --- | --- | ---: | ---: |
| Aside transport 회귀 | 37 tests, OK, 실제 모델 호출 없음 | unittest 12.619초 | 별도 측정 안 함 |
| 현재 전체 Python suite | 1,479 tests, OK, skipped 1 | process 175.95초 / unittest 175.365초 | 전체 gate에서 측정 |
| 전체 release gate 02 | exit 0, 21 checks passed, ready=true | 484.87초 | 239,763,456 |
| 추출 패키지 agent 직렬 fixture | exit 0, peak callback 1, 실제 모델 0회 | 1.20초 | 97,583,104 |
| 추출 패키지 실제 owned Chromium fixture | exit 0, normal pass / defect fail, authored decisions | 12.48초 | 110,051,328 |
| 추출 경로 추가 검사 | 9개 예상 결과 일치, 기본 import/help/doctor/report/integrity | 개별 성능 측정 아님 | 별도 측정 안 함 |

전체 gate 안에서 Chromium driver는 **559 passed / 0 failed**, bridge contract는 **7 passed**였습니다. ZIP·추출·기존 smoke·연구/local/browser journey·실행 후 무결성·current-source-match·validation-inputs-stable가 모두 통과했습니다. 실행 엔진의 25개 agent 회귀도 전체 suite에 포함되며 이 시험들은 실제 모델 실행 수에 포함하지 않습니다.

Python skip 1개는 `ERGO_PAINT_CAPTURES`가 필요한 별도 실제 캡처 사례입니다. 웹 검사의 공유 browser-server handshake와 Python captured-font 분석은 각각 `REMORSEARCH_BROWSER_WS`, `ERGOQA_PYTHON` 미설정으로 제외됐습니다. 이 제한을 통과 수에 섞지 않습니다.

추출 패키지에서 새 Aside 모듈 두 개를 기본 Python으로 import하고 maintainer CLI help를 실행했습니다. 선택적 runtime 없는 doctor는 예상 exit 2, 준비된 환경은 exit 0입니다. 기본 Python으로 원본·추출 경로에서 최종 실제 Pro 보고서를 재조회해 원본 report와 동일함을 확인했고 host-events 해시도 그대로였습니다. 추가 모델/브라우저 dispatch는 없었습니다. 두 relocated fixture의 기본 report와 추가 실행 후 package integrity도 통과했습니다.

실제 Pro 실행의 8개 소스 해시는 현재 repository와 새 추출 package 양쪽에 일치합니다. 보고 결과를 기록하기 위해 gate 이후 수정한 것은 검증 결과 Markdown과 새 JSON입니다. 실행 코드·테스트·배포 package 입력을 변경하지 않았습니다.

독립 export 검사도 파일 30개·소스 해시 8개·독립 대화 2개·모델 12/review 2/probe 2·제품 PNG 10개·provider PNG 0개·두 worker 종료를 확인했습니다. 첫 독립 검사에서는 파일명 prefix가 `model-transcripts.json`까지 잘못 거절해 exit 1이었고, 디렉터리만 검사하도록 바로잡은 검사에서 exit 0이었습니다. 원본 증거와 실행 코드는 바뀌지 않았습니다. 최종 staged diff의 유일한 공백 경고는 원본에서 그대로 복사한 `report.md`의 끝 빈 줄입니다. 이 파일의 원본 바이트와 해시를 보존했으며, 해당 원본 증거를 제외한 파일의 diff 검사는 통과했습니다.


## 충돌 범위와 남은 공백

전체 release gate 실행 중 09:49:04 UTC에 조율자의 [규모 요구사항 handoff](../requirements/swarm-scale-user-clarification-20261112.md)가 추가됐습니다. 개발 세션이 이 파일을 실제 읽었으며, 웹 Pro 개발과 최종 사용자의 작은 모델 수십~수백 persona 운영을 구분해 PRD와 실행 문서에 반영했습니다. 이 전달 문서를 새로운 과금·권한·모델 연결의 승인으로 취급하지 않습니다. 현재 entry/Aside 경로는 2–8개 context이며, 총 persona 수를 큰 큐로 운영하는 계층과 실제 수십~수백 확장 검증은 아직 없습니다. 해당 handoff의 원문은 수정하지 않았습니다.

최초 전체 gate는 Python 1,479개, Chromium 559개, bridge 7개와 relocation/journey 모두 통과했지만 위 새 문서가 실행 중 추가돼 validation-inputs-stable만 실패했습니다. 결과는 exit 1 / ready=false, 483.02초, maxRSS 236,388,352바이트로 그대로 보존합니다. 요구사항을 포함한 새 출력 경로에서 전체 gate를 다시 실행해 exit 0 / 21개 검사 통과를 확인했습니다.

기존 Peekly 작업의 `browser_run.py`, `drivers/web/journey_bridge.mjs`, `session.mjs`, `validate.mjs`, `scripts/check_release.py`와 관련 테스트는 변경하지 않았습니다. `swarm.py`도 그대로입니다. 공유 변경은 이 브랜치의 선택적 `agent_run.py`와 AGENTS/PRD/release/notices/reference 문서입니다. 새 모듈·독립 example·독립 test 위주이며 통합 시 이 문서와 기존 bridge import 계약을 검토해야 합니다.

기존 uncommitted 작업과 모든 다른 worktree를 보존했고 오래된 managed work를 시작·resume·instruct·cancel하지 않았습니다. 사용자 Chrome/화면/키보드를 조작하거나 계정 전환, daemon 설정 변경, 권한 확대를 하지 않았습니다.

남은 범위는 임의 제품의 안전한 동적 탐색 도구, 실제 허용 공개 조사와 persona 생성·적합성 검토의 한 번에 이어지는 제품 실행, persona가 실제 사용자 다양성을 유용하게 대표하는지에 대한 효과 검증, 모델의 PNG 시각 판독, 다양한 locale/UI 변경 대응입니다. 실제 모델 worker를 고의로 강제 중단하고 같은 provider generation의 서버 측 취소까지 입증한 live 시험도 없습니다. 중단/재시작 보장은 현재 local engine의 회귀와 정직한 uncertain 처리 범위입니다.
