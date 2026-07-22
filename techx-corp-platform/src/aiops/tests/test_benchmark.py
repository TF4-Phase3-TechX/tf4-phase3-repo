from benchmark.rcaeval import MetricWindow, parse_case_name, split_metric_name, stratified_sample
from benchmark.scoring import rank_services


def test_rcaeval_case_and_metric_names_are_parsed_without_losing_hyphens():
    label = parse_case_name("re2tt_ts-order-service_disk_2")
    assert label.system == "tt"
    assert label.service == "ts-order-service"
    assert label.fault == "disk"
    assert split_metric_name("ts-order-service_latency-90") == ("ts-order-service", "latency-90")


def test_stratified_sample_is_deterministic_and_covers_systems():
    labels = [
        parse_case_name("re1ss_carts_cpu_1"),
        parse_case_name("re1ss_orders_mem_1"),
        parse_case_name("re1tt_ts-order-service_cpu_1"),
        parse_case_name("re1tt_ts-route-service_mem_1"),
        parse_case_name("re1ob_cartservice_cpu_1"),
        parse_case_name("re1ob_emailservice_mem_1"),
    ]
    first = stratified_sample(labels, 3, seed=7)
    second = stratified_sample(labels, 3, seed=7)
    assert first == second
    assert {label.system for label in first} == {"ss", "tt", "ob"}


def test_baro_lite_ranks_the_shifted_service_first():
    stable = MetricWindow("frontend", "cpu", tuple([10.0] * 60), tuple([10.2] * 60))
    shifted = MetricWindow("checkout", "latency-90", tuple([100.0] * 60), tuple([900.0] * 60))
    rankings = rank_services([stable, shifted])
    assert rankings[0].service == "checkout"
    assert rankings[0].score > rankings[1].score
