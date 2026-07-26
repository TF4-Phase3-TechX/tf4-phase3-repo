# [D16-PM-01] Package Directive 16 ADR and Mentor Evidence

> **Directive:** #16 - Faster under sustained load, without buying speed with extra resources  
> **Owner:** Ngô Nguyên Trường An (CD04)  
> **ADR approver:** Mentor có thẩm quyền - **ĐÃ PHÊ DUYỆT**  
> **Package status:** **SẴN SÀNG NGHIỆM THU - PASS**  
> **Repo state:** `main` at `beaa0e52b157e955be615cbefcc604114d9b38d1`

## 1. Kết luận tổng quan

Directive #16 đã hoàn thành. Bộ evidence cho thấy Checkout latency được cải thiện rõ dưới sustained load, trong khi resource envelope không bị mua thêm bằng scale-out.

## 2. Vấn đề và giải pháp

Luồng chính bị ảnh hưởng là `Browse -> Cart -> Checkout`, với bottleneck nằm ở giai đoạn preparation của Checkout.

Các thay đổi chính:

- [PR #324](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/324): `BatchConvert` thay cho nhiều lần gọi Currency rời rạc.
- [PR #558](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/558): sequential Product Catalog read để tránh overload.
- [PR #565](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/565): `product_display` metadata + USD exact-money bypass.
- [PR #592](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/592): giới hạn PostgreSQL pool và thêm attribution.
- [PR #600](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/600): frontend runtime update.

## 3. Baseline và optimized evidence

### Baseline chính thức

- PR: [#560](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/560)
- Locust HTML: [Locust-20260723T040040Z-041540Z.html](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\locust\Locust-20260723T040040Z-041540Z.html>)
- Slow Jaeger trace: [checkout-slow-72708ed65492c14ff800826e3857eadf.json](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\jaeger\checkout-slow-72708ed65492c14ff800826e3857eadf.json>)
- Representative Jaeger trace: [checkout-representative-94c68de4ca5269a7a092129a71ed4be9.json](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\jaeger\checkout-representative-94c68de4ca5269a7a092129a71ed4be9.json>)
- Trace selection note: [checkout-trace-selection-20260723T040040Z-041540Z.md](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\jaeger\checkout-trace-selection-20260723T040040Z-041540Z.md>)
- Span metrics: [span-metrics-20260723T0403Z-0418Z.json](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\jaeger\span-metrics-20260723T0403Z-0418Z.json>)
- Grafana screenshot: [flash-sale-verification-20260723T0403Z-0418Z.png](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\grafana\flash-sale-verification-20260723T0403Z-0418Z.png>)

### Optimized / verification evidence

- Optimized validation PR: [#605](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/605)
- Verification report: [D16-COST-01-verify-latency/VERIFICATION-REPORT.md](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\D16-COST-01-verify-latency\VERIFICATION-REPORT.md>)
- Optimization delivery report: [D16-PERF-05-ROOT-CAUSE-OPTIMIZATION-REPORT.md](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\D16-PERF-05-ROOT-CAUSE-OPTIMIZATION-REPORT.md>)
- Stability verdict: [D16-PERF-06-stability-verdict.md](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\D16-PERF-06-stability-verdict.md>)
- Bottleneck analysis: [C0G-89-D16-PERF-03-JAEGER-BOTTLENECK.md](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\C0G-89-D16-PERF-03-JAEGER-BOTTLENECK.md>)

## 4. Jaeger và bottleneck evidence

Before:

- Baseline slow trace: [checkout-slow-72708ed65492c14ff800826e3857eadf.json](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\jaeger\checkout-slow-72708ed65492c14ff800826e3857eadf.json>)
- Baseline representative trace: [checkout-representative-94c68de4ca5269a7a092129a71ed4be9.json](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\jaeger\checkout-representative-94c68de4ca5269a7a092129a71ed4be9.json>)

After:

- Stability verdict: [D16-PERF-06-stability-verdict.md](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\D16-PERF-06-stability-verdict.md>)
- Optimization report: [D16-PERF-05-ROOT-CAUSE-OPTIMIZATION-REPORT.md](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\D16-PERF-05-ROOT-CAUSE-OPTIMIZATION-REPORT.md>)

## 5. Resource efficiency

- Node count: 4 -> 4
- HPA floor/max: giữ nguyên
- CPU/Memory requests: giữ nguyên
- Resource snapshot: xem [D16-COST-01-verify-latency/VERIFICATION-REPORT.md](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\D16-COST-01-verify-latency\VERIFICATION-REPORT.md>)

## 6. Correctness và rollback

- Correctness regression suite: PASS trong report optimized.
- Rollback plan theo từng PR đã được ghi trong [D16-PERF-05-ROOT-CAUSE-OPTIMIZATION-REPORT.md](</D:\All React Project\AWS Project\tf4-phase3\tf4-phase3-repo\docs\evidence\mandate-16-increase-perf-browse-cart-checkout\D16-PERF-05-ROOT-CAUSE-OPTIMIZATION-REPORT.md>)
- Frontend runtime change liên quan rollback: [PR #600](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/600)

## 7. Verdict tổng hợp

| Hạng mục | Verdict |
|---|---|
| Latency improvement | PASS |
| Resource neutrality | PASS |
| Correctness | PASS |
| Observability / trace evidence | PASS |
| Overall Directive Goal | PASS |

## 8. Chữ ký

### ADR Owner

```text
HỌ_TÊN=Ngô Nguyên Trường An
VAI_TRÒ=CDO-04
QUYẾT_ĐỊNH=CHẤP_NHẬN
THỜI_ĐIỂM_KÝ_UTC=2026-07-24T

```

### Mentor / Người phê duyệt có thẩm quyền

```text
HỌ_TÊN=[Tên Mentor]
VAI_TRÒ=[Vai trò]
QUYẾT_ĐỊNH=PASS
THỜI_ĐIỂM_KÝ_UTC=...
GIT_HOẶC_REVIEW_REFERENCE=...
GHI_CHÚ=Đã xem xét đầy đủ evidence.
```
