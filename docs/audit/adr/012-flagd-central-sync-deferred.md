# ADR-012: flagd Central Flag Sync Deferred — Risk Ghi Nhận

**Ngày:** 2026-07-09
**Trạng thái:** Accepted — URGENT, cần fix ngay
**Người quyết định:** CDO-04 (Infrastructure)
**Người review:** CDO-07 (Audit), toàn TF4
**Pillar liên quan:** Auditability, Reliability
**Source:** `deploy/values-flagd-sync.yaml`, `techx-corp-chart/values.yaml`
**Refs:** `docs/evidence/epic-02-baseline-architecture/03-external-services-cost-control-layer.md` (Assumption 5), ARCH-RISK-05

---

## 1. Bối cảnh (Context)

Theo kiến trúc TF4 và luật Phase 3 (RULES.md):

- **Central Flag Configuration** là nguồn flag tập trung do BTC kiểm soát — bên ngoài EKS.
- **flagd** trong cluster nhận read-only sync từ Central Flag Configuration.
- Đây là cơ chế BTC dùng để **inject incident** vào hệ thống của TF4.
- **Bypass, tắt, hoặc disconnect flagd khỏi Central Flag = DISQUALIFY.**

Luồng thiết kế:
```
Central Flag Config (BTC) → flagd (read-only sync) → services (OpenFeature hooks)
```

---

## 2. Trạng thái hiện tại — Central Sync ĐANG BỊ VỠ

Từ `deploy/values-flagd-sync.yaml`:

```yaml
# Central flag sync stays DEFERRED until token + compatible flagd args are confirmed.
components:
  flagd:
    sidecarContainers: []
    # Previous central-sync attempt kept for later reference; DO NOT uncomment until tested.
    # It crashes today because ghcr.io/open-feature/flagd:v0.12.9 has no /bin/sh.
    # command:
    #   - "/bin/sh"
    #   ...
    #   --sources '[{"uri":"https://...","provider":"http",...}]'
```

**Kết quả thực tế:** flagd đang chạy với **local demo.flagd.json** thay vì Central Flag Config của BTC.

```yaml
# values.yaml — flagd hiện tại
command:
  - "/flagd-build"
  - "start"
  - "--uri"
  - "file:./etc/flagd/demo.flagd.json"   # ← local file, không phải central
```

---

## 3. Tại sao bị deferred (Rationale)

| Lý do kỹ thuật | Giải thích |
|---|---|
| `flagd:v0.12.9` không có `/bin/sh` | Shell wrapper command bị crash khi execute |
| Token chưa được xác nhận | BTC chưa cấp token hoặc token chưa được test |
| Compatible flagd args chưa rõ | Cần verify cú pháp `--sources` với version hiện tại |

---

## 4. Rủi ro (Known Risks)

| Risk | Impact | Urgency |
|---|---|---|
| BTC không inject được incident vào TF4 | BTC có thể penalize TF4 | **CRITICAL** |
| TF4 không nhận được incident injection | Không có cơ hội thể hiện incident response | High |
| Khi BTC kiểm tra định kỳ, phát hiện flagd không sync | Vi phạm luật Phase 3 | High |
| Local demo.flagd.json là file tĩnh | Không reflect real-time BTC flag changes | High |

> ⚠️ **CDO-07 ghi nhận:** Đây là rủi ro vi phạm luật chơi nghiêm trọng nhất trong hệ thống hiện tại. Không phải bug kỹ thuật — là vấn đề governance.

---

## 5. Fix Plan (CDO-04 owns — URGENT)

**Option A — Upgrade flagd image:**
```yaml
flagd:
  imageOverride:
    repository: "ghcr.io/open-feature/flagd"
    tag: "v0.13.x"   # Version có /bin/sh hoặc native --sources support
```

**Option B — Dùng native flagd args không cần /bin/sh:**
```yaml
flagd:
  command:
    - "/flagd-build"
    - "start"
    - "--port"
    - "8013"
    - "--ofrep-port"
    - "8016"
    - "--uri"
    - "http://122.248.223.194.sslip.io/flags.json"
  env:
    - name: FLAGD_SYNC_TOKEN
      valueFrom:
        secretKeyRef:
          name: flagd-sync
          key: token
```

**CDO-07 verify sau fix:**
```bash
# Verify flagd đang sync từ central source
kubectl -n techx-tf4 logs deploy/flagd | grep -i "sync\|source\|uri"
# Expected: log showing HTTP sync from central endpoint, not local file

# Verify BTC flag có thể thay đổi
# BTC bật một flag → check service behavior thay đổi
```

---

## 6. Tham chiếu (References)

- `deploy/values-flagd-sync.yaml` — Central sync config hiện tại (deferred)
- `techx-corp-chart/values.yaml` — flagd command với local file
- `docs/requirements/RULES.md` — Luật Phase 3: bypass flagd = disqualify
- `docs/evidence/epic-02-baseline-architecture/03-external-services-cost-control-layer.md` — Central Flag arch
- `docs/evidence/epic-02-baseline-architecture/04-architecture-assumptions.md` — Assumption 5
- `docs/evidence/epic-02-baseline-architecture/05-architecture-risk-register.md` — ARCH-RISK-05
