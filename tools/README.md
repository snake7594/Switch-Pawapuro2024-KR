# tools/ 안내

이 폴더에는 프로젝트 전 과정에서 쓰인 파이썬 도구가 **모두** 들어 있습니다.
지금 빌드에 필요한 것은 맨 위 표의 몇 개뿐이고, 나머지는 **작업 기록**입니다.

모든 스크립트는 **작업공간**을 기준으로 동작합니다. 환경변수로 지정하세요.

```bash
set PAWA_ROOT=D:\pawa_ws      # 미지정 시 현재 디렉터리를 작업공간으로 사용
```

> 저장소에 담으면서 옛 절대경로(`C:\Users\...\실황2024`)는 `PAWA_ROOT` 기준으로 자동 치환했습니다.
> 다만 오래된 스크립트 중에는 지금은 없는 중간 산출물(`main-safe20`, `_scene_tr_*.json` 등)을
> 요구하는 것이 있어 그대로 실행되지 않을 수 있습니다. 읽고 참고하는 용도로 보세요.

## 지금 쓰는 도구

| 파일 | 역할 |
|---|---|
| `SETUP_WORKSPACE.py` | 작업공간 구성(원본 MD5 검증 · 데이터 배치 · 베이스 exe 생성) |
| `BUILD_BASE.py` | ★ 베이스 exe = 원본 + 죽은 zero-run 풀에 `exe_pool` 전체 문장 기록 + 포인터 리다이렉트 |
| `BUILD_EXE.py` | ★ 실행파일 빌드. 원본영역 주입 + 꼬리풀 완성문장 리다이렉트 + 자체검증 (버전 상수 자동 유도) |
| `BUILD_RDB_FROM_MASTER.py` | ★ RDB 빌드. 마스터 텍스트 주입 + 잔차 팩(폰트·이미지) 적용 |
| `VERIFY_EXE.py` | 빌드된 exe 구조·참조·풀·서식·잔존 검증 |
| `VERIFY_RDB.py` | 빌드된 RDB 전 슬롯 무결성 + 폰트/텍스트 확인 |
| `BUILD_FONT_2ND.py` | 새로 생긴 폰트 CHK에 한글 글리프 주입 |
| `BUILD_RESIDUAL.py` | 잔차 팩 재생성(없어진 파일 제거 · 새 폰트 추가) |
| `rdblib.py` | RDB/RDI 포맷 라이브러리(암복호화 · zlib · 재배치). 다른 도구들이 import |
| `port/` | 게임 업데이트 간 좌표 이식 도구 → [../docs/PORTING.md](../docs/PORTING.md) |
| `VERIFY_BUILD.py` / `APPLY_MASTER.py` | 구 경로(게임 v1.8.0 기준값·하드코딩 경로 주의) |
| `BUILD_FROM_MASTER.py` | ⛔ 구 exe 빌더. 게임 v1.8.0 상수가 하드코딩되어 있음 → `BUILD_EXE.py` 사용 |

## 분석·검사

| 파일 | 역할 |
|---|---|
| `POOL_MEASURE.py` | 꼬리풀(빈 공간) 용량 측정 |
| `SCAN_RDB_LINE.py` | RDB 텍스트의 줄 규칙(24자/3줄) 위반 수집 |
| `_nso_audit.py`, `_exe_refscan.py`, `_reloc_check.py` | NSO 구조·참조·재배치 테이블 점검 |
| `_uncdfont_dump.py`, `_glyph_table_diff.py` | 폰트(UNCDFONT) 구조 덤프·비교 |
| `_verify_repack_out.py`, `FINAL_VERIFY.py`, `_plaus.py` | 주입 결과 검증·오탐 판정 |
| `analyze_exe_expand.py`, `analyze_pcrel.py` | 확장 가능성·PC상대 참조 분석 |

## 추출

| 파일 | 역할 |
|---|---|
| `extract_jp_text.py`, `add_exe_text.py` | 일본어 텍스트 전수 추출(CHK STRING 청크 + NSO .rodata) |
| `UNPACK_RES00.py` | RDB에서 CHK 파일 꺼내기 |
| `EXTRACT_MYLIFE.py`, `EXTRACT_ALL_SCENES.py`, `SCENE_EXTRACT.py` | 대사 씬 재구성(RELA 연속 슬롯 → 대본) |
| `EXTRACT_EXE_EXT.py` | 배포본 실행파일에서 완성 문장 역추출 → 마스터에 반영 |
| `BUILD_MASTER_EXE.py`, `BUILD_MASTER_RDB.py`, `MERGE_MASTER.py` | 배포본 역추출로 통합 마스터 생성 |

## 주입·수리 (과거 파이프라인)

`inject_all.py` `inject_lib.py` `STRING_INJECT_INPLACE.py` `SEN_*` `NXSUR_LABEL_INJECT.py`
`PATCH_*` `FIX_*` `REPAIR_*` `RECODE_*` `REINJECT_*` `FINALIZE_*` `SCENE_INJECT.py`
`RUBY_APPLY_TO_MASTER.py` `UPDATE_MASTER_LINEFIT.py` `CANCEL_BAD_EXT.py` 등

지금은 `번역_마스터.json` 하나로 통합되어 **직접 쓸 일은 없습니다.** 당시 무엇을 어떻게 고쳤는지
남겨 둔 기록입니다. 특히 참고할 만한 것:

- `FIX_JOSA.py` — 조사 병기(`이(가)`)를 앞 글자 받침에 맞춰 확정
- `RUBY_APPLY_TO_MASTER.py` — 후리가나(루비) 잔존 제거
- `BUILD_FONT_TSV.py`, `BUILD_FONT_ONLY.py` — 한글 폰트 재구축
- `REPACK_AUTO.py` — RDB 재패킹(크기 변동 시 자동 재배치 + RDI 갱신)

## ⛔ 쓰면 안 되는 것

| 파일 | 이유 |
|---|---|
| `EXPAND_NSO.py` | 실행파일 세그먼트 확장. 부팅은 되지만 **마이라이프 28일차에서 게임이 죽습니다.** 정적으로 모든 참조를 갱신하는 것이 원리적으로 불가능합니다 |
| `INJECT_MYLIFE_EXPAND.py`, `INJECT_ALL_EXPAND.py` | 위 확장 방식을 전제로 한 주입 |
| `INJECT_MYLIFE.py` | rodata의 0 영역을 **조건 없이** 빈 공간으로 사용 → 셰이더 디스크립터 침범으로 **게임 시작 직후 GPU 크래시** ([HISTORY §6](../docs/HISTORY.md)) |

> ⚠ `SAFE_REDIRECT.py` 는 **금지 목록이 아닙니다.** 데이터포인터 타깃·코드참조 페이지를 배제하고
> 양끝 32B를 예약하는 조건부 zero-run 풀로, 이 조건이 붙은 버전(v2)이 실제 배포본에 들어가
> 검증되었습니다. 현재는 `BUILD_BASE.py` 가 같은 공법을 마스터(`exe_pool`) 기준으로 재구현합니다.
> 위험한 것은 **조건 없이 0 영역을 쓰는 것**입니다.

자세한 경위는 [../docs/HISTORY.md](../docs/HISTORY.md).
