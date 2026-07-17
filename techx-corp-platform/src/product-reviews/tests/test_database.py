import os
import pytest
from unittest.mock import patch, MagicMock

os.environ["DB_CONNECTION_STRING"] = "fake_connection_string"

mock_pool_patcher = patch("psycopg2.pool.ThreadedConnectionPool")
MockThreadedConnectionPool = mock_pool_patcher.start()

mock_db_pool = MagicMock()
MockThreadedConnectionPool.return_value = mock_db_pool

import database


@pytest.fixture
def mock_cursor():
    cursor = MagicMock()
    return cursor


@pytest.fixture
def mock_connection(mock_cursor):
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = mock_cursor
    return conn


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset các mock sau mỗi bài test để không bị nhiễu dữ liệu."""
    mock_db_pool.reset_mock()
    yield


class TestDatabaseConnectionPool:
    def test_get_db_connection_success(self, mock_connection):
        """Test mượn và trả kết nối thành công (Happy path)."""
        mock_db_pool.getconn.return_value = mock_connection

        with database.get_db_connection() as conn:
            assert conn == mock_connection

        mock_db_pool.getconn.assert_called_once()
        mock_db_pool.putconn.assert_called_once_with(mock_connection)

    def test_get_db_connection_with_exception(self, mock_connection):
        """Test mượn kết nối nhưng bị lỗi giữa chừng, đảm bảo putconn VẪN được gọi (Zero Leakage)."""
        mock_db_pool.getconn.return_value = mock_connection

        with pytest.raises(ValueError, match="Fake SQL Error"):
            with database.get_db_connection() as conn:
                raise ValueError("Fake SQL Error")

        mock_db_pool.getconn.assert_called_once()
        mock_db_pool.putconn.assert_called_once_with(mock_connection)


class TestDatabaseQueries:
    def test_fetch_product_reviews_from_db(self, mock_connection, mock_cursor):
        """Test hàm fetch_product_reviews_from_db gọi đúng câu SQL và trả về dữ liệu."""
        mock_db_pool.getconn.return_value = mock_connection
        
        mock_records = [
            (1, "john", "good", 4.5),
            (2, "alice", "bad", 2.0)
        ]
        mock_cursor.fetchall.return_value = mock_records

        result = database.fetch_product_reviews_from_db("PROD123")

        mock_cursor.execute.assert_called_once()
        args, kwargs = mock_cursor.execute.call_args
        assert "SELECT id, username, description, score FROM reviews.productreviews WHERE product_id= %s" in args[0]
        assert args[1] == ("PROD123",)
        
        assert result == mock_records
        mock_db_pool.putconn.assert_called_once_with(mock_connection)

    def test_fetch_avg_product_review_score_has_data(self, mock_connection, mock_cursor):
        """Test tính điểm trung bình khi sản phẩm CÓ lượt review."""
        mock_db_pool.getconn.return_value = mock_connection
        mock_cursor.fetchall.return_value = [(4.56,)]

        result = database.fetch_avg_product_review_score_from_db("PROD123")

        assert result == "4.6"  # Đảm bảo làm tròn 1 chữ số thập phân
        mock_db_pool.putconn.assert_called_once_with(mock_connection)

    def test_fetch_avg_product_review_score_no_data(self, mock_connection, mock_cursor):
        """Test tính điểm trung bình khi sản phẩm KHÔNG CÓ review (hoặc None)."""
        mock_db_pool.getconn.return_value = mock_connection
        
        mock_cursor.fetchall.return_value = [(None,)]

        result = database.fetch_avg_product_review_score_from_db("PROD123")

        assert result is None
        mock_db_pool.putconn.assert_called_once_with(mock_connection)
