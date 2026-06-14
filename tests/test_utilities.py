from chalk.util.sequence import unique


class TestSequence:
    def test_unique_preserve_order(self) -> None:
        assert list(unique([1, 2, 3])) == [1, 2, 3]
        assert list(unique([1, 2, 2, 3])) == [1, 2, 3]
        assert list(unique([1, 2, 2, 3, 2, 1])) == [1, 2, 3]
