from konsistent.core.format_time import format_time


class TestFormatTime:
    def test_formats_sub_second_times_as_milliseconds(self) -> None:
        assert format_time(0) == "0ms"
        assert format_time(1) == "1ms"
        assert format_time(42) == "42ms"
        assert format_time(999) == "999ms"

    def test_rounds_fractional_milliseconds(self) -> None:
        assert format_time(1.4) == "1ms"
        assert format_time(1.5) == "2ms"
        assert format_time(99.9) == "100ms"

    def test_formats_times_at_least_one_second_as_seconds_with_one_decimal(self) -> None:
        assert format_time(1000) == "1.0s"
        assert format_time(1500) == "1.5s"
        assert format_time(2345) == "2.3s"
        assert format_time(10_000) == "10.0s"

    def test_formats_exactly_999ms_as_milliseconds(self) -> None:
        assert format_time(999) == "999ms"

    def test_formats_exactly_1000ms_as_seconds(self) -> None:
        assert format_time(1000) == "1.0s"
