# UX 제품 제어 구현·검증 기록 — 2026-11-19 (KST)

## 판정

**구현 소스의 로컬 회귀검사와 패키지 검사는 통과했다. 전체 제품 완료/릴리스 준비 완료는 아니다.**
실제 호스트 선택창, Astra ultra 실행, 브라우저 사용자 경로, 실제 이미지·영상 및 인간 사용성 효과는 미검증이다.
기존 릴리스 검사의 최종 값은 `ready: false`, `published: false`이다.

검사한 구현 HEAD는 `4fb693d51f597aa811d6925f58d5285771609445`이다.
이 기록과 측정 JSON은 검사 종료 후 문서 전용 커밋으로 추가했다. 이후 구현 소스는 바꾸지 않았다.
원격 반영은 `git ls-remote`로 검증하며, 이 파일 자체가 포함된 SHA는 Git 커밋 기록에서 확인한다.

## 실제 저장소와 보존한 기준

| 구분 | 경로/HEAD | 처리 |
| --- | --- | --- |
| 이번 구현 | 승인 경로 `/remorsearch-ux-qa`; 네이티브 `/Volumes/SanDisk2TB/m4mini/CodeProjects/Remorsearch_UX_QA_Skill`; 브랜치 `rem/ux-product-controls-20261119` | 원격 기준 `f60d79d3c31aff57a51d82ab041cb68da1fb2ff0`에서 시작; 본인 변경만 커밋/푸시 |
| 최신 별도 개발 작업트리 | `/remorsearch-ux-qa/.worktrees/peekly-ux-findings-20261113/.worktrees/peekly-verdict-quality-20261113`; `982958e9f1fbbe2c058f9b6d8b8147add7565d1a` | 읽기 전용 대조. clean, 로컬 tracking 대비 ahead 46 유지 |
| 최신 작업트리의 네이티브 경로 | `/Volumes/SanDisk2TB/m4mini/CodeProjects/Remorsearch_UX_QA_Skill/.worktrees/peekly-ux-findings-20261113/.worktrees/peekly-verdict-quality-20261113` | 머지/리셋/실행/일괄 푸시하지 않음 |

최신 로컬과 공개 기준 사이의 차이 13개 파일을 확인했다.
관련 소스 차이는 `uxpersonas/peekly_criteria.py`의 현재 저장 오류 문구와
`uxpersonas/scale_run.py`의 prerequisite 순서/제한된 관측 payload 처리다.
030 수리 및 재판정과 관련한 이 변경을 덮어쓰지 않았다.
AGENTS/PRD/SKILL은 두 기준 사이에서 동일했다.

실제 읽은 주요 규칙·구현은 `AGENTS.md`, `PRD.md`, `HANDOFF.md`,
`docs/release.md`, `docs/architecture.md`, 스킬 진입점과 관련 reference,
기존 `uxloop`, `uxpersonas`, `uxresearch`, `ergoqa/hf`, 해당 테스트와 릴리스 검사다.
14개 요구별 경로/상태/미완료 조건은 [요구 추적표](../requirements/ux-controls-20261119.md),
OSS/API·라이선스·논문 표본/효과/한계와 설계 결정은
[일차 출처 비교](../human-factors/2026-11-19-reuse-review.md)에 기록했다.

## 기존 cohort 증거의 확인 범위

최신 작업트리의 `docs/validation/peekly-coverage-completion-20261115/cohort-20261116/cohort-receipt.md`,
JSON과 build provenance를 읽었다. JSON SHA-256:
`b37b7d0948e205e9dce0407cfb8380895cd3ee3e7fa5da766aa343d96348efc9`.

- receipt: 최종 32세션, 136기준 = passed 113 / not_applicable 23; 인용 증거 1,196개, 누락/해시 차이 0.
- 사용자의 별도 읽기 전용 8개 SQLite 확인: complete 39 / uncertain 7 / running 0 / queued 0.
- 이번 작업에서 두 실제 엔진 파일의 해시를 receipt 값과 비교해 일치함을 확인했다.
- 이번 작업에서 8개 DB 전체나 1,196개 증거를 다시 읽고 재해시한 것은 아니다.
- 저장 증거 무결성은 새 브라우저 실험이나 새 UX 개선 효과가 아니다.
- 7 uncertain을 삭제·자동 재전송하지 않았고, 030의 수리된 최신 판정을 오래된 blocked 서술로 바꾸지 않았다.

## 구현 단위와 의존성

경로의 `skill/`은 `skills/remorsearch-ux-qa/`를 뜻한다.

| 단위 / 커밋 | 변경 경로 | 기존 의존성 / 구현 완료 조건 | 실제 검사 |
| --- | --- | --- | --- |
| 1 / `6596f1c549e9c78c1bb8dd588e184fa2fb4e55f5` | 요구·연구 문서, `skill/uxpersonas/data/korea-seeds.v1.json`, `skill/THIRD_PARTY_NOTICES.md`, reach 설명 | 공식 API 32개 성인 합성 행의 출처/revision/응답 해시/CC BY 4.0·변경 고지. 기존 인체 모델 수치 유지 | 원본 API 응답·자료 확인; seed 검사는 뒤의 전체 회귀검사에 포함 |
| 2 / `b2bcc59cd2df40b58e89717fc89a297186e881c7` | `skill/uxloop/{rollback,cli,engine,patching,storage}.py`, `tests/test_loop_rollback.py` | 기존 checkpoint/잠금/atomic_bytes/replay 재사용. 명시 선택·해시·의존성·충돌·재시작 검사. 단일 파일 범위 | 초기 14개, 보강 17개 검사 통과; 최종 18개 및 전체 검사 통과 |
| 3 / `b4acb7fc2b98f5a332b0a12b3b2e1d5edb968e6d` | `skill/uxpersonas/{product_controls,cli,scale_entry,scale_run}.py`, SKILL/reference, `tests/test_product_controls.py` | 기존 Library·불변 queue plan·dispatch에 현재 PRD/UI/persona/model 선택 연결. 모델 호출·렌더러 생성 없음 | 선택 21개, reading budget 13개 통과; 첫 릴리스 전체 1,945개(21 skipped), 웹 외 검사 통과 |
| 4 / `4fb693d51f597aa811d6925f58d5285771609445` | product_controls/rollback 및 양쪽 테스트·관련 문서 | 잘못된 seed 목록 타입 차단. 메타데이터 없는 삭제 원본의 재생성을 신규/복구 경로 모두에서 차단 | 선택 22개, 롤백 18개 통과; 아래 최종 전체 검사 |
| 5 / 문서 전용 | 이 기록, 측정 JSON, 검사 receipt | 소스 변경 없이 실제 결과/범위/차단/다음 단위 기록 | JSON parse·수치 및 파일 해시 비교, git diff --check |

### 실제 실행 연결과 아직 없는 연결

`configure/select`의 명시 응답은 `prepare_scale_goal(selection=...)`을 통해 기존 queue plan에
보관되고 open/dispatch에서 다시 검증된다. 새 live 계획에는 선택이 필요하다.
취소/무응답은 실행·비용 승인이 아니다. 기존 historical queue는 다시 쓰거나 재전송하지 않는다.
호스트의 모델 identity, adapter hash와 reasoning effort attestation을 요구한다.
Astra ultra라는 라벨만으로 다른 경로를 허용하지 않으며 이번 작업은 실제 모델을 호출하지 않았다.

`request_selection(spec, ask)`는 기존 호스트 UI가 구현할 callback 계약이다.
실제 선택창 renderer가 만들어졌다는 뜻이 아니다. `ui_rendered: false`가 유지된다.
`check_style_scope`는 선언한 파일·속성 범위를 검사한다.
CSS AST/import graph와 최종 computed style 검사는 아직 없으며 `computed_css_verified: false`다.

개선 리포트에는 이유·기대효과·경로·시나리오·Figma/replay 근거와 롤백 가능 여부를 넣었다.
기대효과를 실측 효과로 표시하지 않는다.
롤백은 선택 이후 변경된 내용, 누락 원본, 의존 개선, pending forward intent를 검사한다.
둘 이상의 파일을 바꾸는 롤백과 메타데이터 없는 삭제 원본 복원은 쓰기 전에 거절한다.
잠금은 협력하는 writer 범위이며, 임의의 외부 프로세스에 대한 filesystem CAS는 아니다.
성공한 롤백도 과거 완료 판정을 무효화하며 기존 replay와 인접 회귀검사를 새 근거로 해야 한다.

## 최종 검사

명령:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_release.py --skip-web --output dist/ux-controls-20261119-final
```

| 검사 | 실제 결과 |
| --- | --- |
| Python | 3.15.2 |
| 전체 unittest | 1,947개 / 299.669초; 실패 0, 오류 0, skipped 21 (1,926개 실행) |
| 릴리스 checker | 종료 코드 1; 19개 check 중 18개 통과, 웹 1개 skipped |
| 준비/게시 | ready=false, published=false |
| 패키징·무결성 | release files, bundle build/integrity, extracted integrity 통과 |
| 설치 위치 이동 후 실행 | runtime discovery, CLI/reference, smoke, local/research journey, authored scale fixture/status 통과 |
| 검사 입력 | current-source-match 및 validation-inputs-stable 통과; 실행 중 소스 변경 없음 |
| 실제 웹·선택창·모델·손 영상 | 미실행/미검증 |
| 실제 사람 사용성 | 미측정 |
| 알려진 경고 | 전체 테스트 로그에 unclosed SQLite ResourceWarning 88개 행 존재; 모든 경고의 allocation origin을 이번에 추적한 것은 아님 |

첫 전체 개발 검사는 새 테스트의 read-only provider 속성 설정 오류와 기존 문서 읽기 예산 초과를
발견했다. 테스트 sentinel을 수정하고 설명을 줄여 기존 제한 내로 맞췄다.
8,192/42,000 byte 예산 자체를 높이지 않았다. 이후 해당 검사와 전체 검사를 다시 실행했다.

원본 결과는 승인된 기존 checkout의 `dist/ux-controls-20261119-final/validation.json`,
`dist/ux-controls-20261119-final/logs/`, `.ux-loop/ux-controls-release-final.log`에 남겼다.
주요 파일의 해시·검사 목록은 함께 커밋한 [검사 receipt](ux-controls-20261119-receipt.json)에 있다.
실제 출력의 `published:false`는 릴리스 배포 상태다. Git feature branch push와는 별개다.

## 제한된 성능 측정

[30쌍 원자료](ux-controls-20261119-benchmark.json)는 동일한 Mac mini에서 3 warm-up 후
순서를 번갈아 30쌍을 측정한 오프라인 내부 연산 비교다.
동일한 32개 authored task projection의 결과가 같은지 확인한 뒤,
각 projection마다 PRD/UI/설정을 재검증하는 호출과 한 번 검증한 후 projection을 재사용하는
새 내부 경로를 비교했다. 과거 릴리스 전체 또는 브라우저 사용 속도를 비교한 것이 아니다.

| 측정 | 반복 검증 경로 | 한 번 검증 후 재사용 |
| --- | ---: | ---: |
| p50 | 59.710 ms | 2.108 ms |
| p95, nearest-rank | 99.095 ms | 3.138 ms |
| Python tracemalloc peak | 63,846 bytes | 39,155 bytes |

측정 소스 SHA-256:
`665cce0b54d810556ca496f8ed2f15dba104eb86ea10835e3a2c637d5e16b5b2`.
실제 모델 호출 0, 브라우저 실행 없음, 인간 사용성 측정 없음.
호스트의 다른 부하는 통제하지 않았다. tracemalloc은 RSS/브라우저 메모리가 아니다.
따라서 이 결과로 전체 제품의 성능·메모리·UX 인수 기준이 충족됐다고 판단하지 않는다.

## 최신 로컬과의 호환성 확인

다음 읽기 전용 검사는 구현 HEAD에서 종료 코드 0이었다.

```sh
git diff --no-ext-diff --binary f60d79d3c31aff57a51d82ab041cb68da1fb2ff0 HEAD |
git -C .worktrees/peekly-ux-findings-20261113/.worktrees/peekly-verdict-quality-20261113 apply --check -
```

이는 패치 적용 가능성 검사다. 실제 머지, 최신 982958e에서의 통합 실행, 브라우저 회귀 통과를
뜻하지 않는다. 최종 문서 커밋 후에도 같은 검사를 재확인한다.

## 차단과 후속 단위

현재 설치된 기본 Node는 24.21.0이며 기존 driver 계약에 필요한 Node 22를 runtime discovery에서
찾지 못했다. 허용된 CUA 호출 계약도 managed-work 연결을 요구하지만 이 대화에는 해당 연결이
없다. 기존 권한 거절을 우회하거나 work.start/새 환경/새 모델 worker를 만들지 않았다.
따라서 실제 브라우저와 선택창 결과를 만들거나 확인했다고 보고할 근거가 없다.

사용자가 Dots에서 Astra ultra만으로 후속 분업할 때 다음 순서로 진행한다.
이 문서는 새 실행이나 비용 승인을 만들지 않는다.

| 다음 단위 | 경로·기존 연결 | 의존성과 완료 조건 |
| --- | --- | --- |
| A. 최신 소스 통합 | 위 별도 최신 worktree + 본 feature commits | 소유권 있는 별도 작업트리에서 선택 적용. 기존 46개 일괄 push 금지. 030 수리 유지, 전체 Python/기존 release gate 재검증 |
| B. 실제 선택 UI/모델 연결 | 기존 Dots renderer, `product_controls.py`, `scale_entry.py` | 선택 인원/ID/revision/model/effort가 queue/dispatch와 일치. cancel·변경 후 만료·초점·Tab/Shift-Tab·Escape·focus return 실제 검증. 승인된 Astra ultra attestation과 비용 gate |
| C. UI 기준선·CSS 경계 | 대상 PRD/Figma, 기존 compiler, driver | 타깃 실제 CSS Modules graph/global/composes/shared token 및 computed style 검사. 기준/후보 화면과 실제 과업·인접 화면/a11y 회귀 |
| D. 관측 영상·인체 보정 | 기존 snapshot/device/profile, `ergoqa/hf` | 승인된 실제 frame/시간/그립/기기 치수와 보정·불확실성. 관측/모델 추정/unknown 구분. 가려짐/반사/좌우·방향 처리. 합성 배경에서 신체 속성 추정 금지 |
| E. 측정 기반 연구 루프 | 기존 uxresearch/ergo_experiments/uxloop | 출처 버전→가설→사전 수용 기준→분리된 보정/평가 자료→실험→채택/기각/보류→회귀. 시간/비용/호출/저장/반복 한도와 중단 사유 보존 |
| F. 다중 파일 롤백 | 기존 host publication transaction이 있을 때만 | 원자적 다중 파일 교체·원본 메타데이터·동시 변경 보존의 실제 근거. 없으면 현재 지원 불가 상태 유지 |

성능 수용 기준은 연구 문서의 **제안된 기준**이다: 같은 기기의 warm-up 분리·30개 이상 paired
표본, p50/p95·RSS·bundle/artifact bytes, 과업 성공/오류/복구, 접근성 검사.
p95/RSS 5% 초과 악화 없음은 아직 전체 제품에서 측정·충족한 결과가 아니다.
합성 fixture와 저장된 cohort는 실제 인간 효과의 대체 자료가 아니다.
