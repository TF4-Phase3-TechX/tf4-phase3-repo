import os
import pytest
from psycopg2 import pool
from unittest.mock import MagicMock

# Đảm bảo environment variable luôn có mặt để không lỗi os.environ.get
os.environ["DB_CONNECTION_STRING"] = "fake_connection_string"
os.environ["DB_MAX_CONN"] = "20"

import database

def test_get_db_connection_success(mocker):
    # Chặn hàm getconn lại, ép nó trả về một chuỗi ký tự (giả làm connection)
    mock_getconn = mocker.patch('database.db_pool.getconn', return_value="fake_connection")
    
    # Chặn hàm putconn lại để nó không thực sự trả gì về Database thật
    mock_putconn = mocker.patch('database.db_pool.putconn')

    # Chạy hàm thực tế
    with database.get_db_connection() as conn:
        assert conn == "fake_connection"  # Đảm bảo lấy đúng đồ giả

    # Xác minh: Đảm bảo getconn và putconn đều được gọi chính xác 1 lần
    mock_getconn.assert_called_once()
    mock_putconn.assert_called_once_with("fake_connection")

def test_get_db_connection_exhausted(mocker):
    # Dùng side_effect để ép hàm văng lỗi PoolError mỗi khi được gọi
    mock_getconn = mocker.patch('database.db_pool.getconn', side_effect=pool.PoolError)
    
    # Ép hàm time.sleep thành một hàm rỗng (không làm gì cả)
    mock_sleep = mocker.patch('time.sleep')
    mock_putconn = mocker.patch('database.db_pool.putconn')

    # Kỳ vọng hệ thống sẽ tự ném ra lỗi sau khi cạn kiệt 3 lần thử
    with pytest.raises(pool.PoolError, match="Không thể lấy kết nối từ Database sau nhiều lần thử."):
        with database.get_db_connection():
            pass

    # Xác minh: Kiểm tra vòng lặp retry có chạy đủ 3 lần như thiết kế không
    assert mock_getconn.call_count == 3
    assert mock_sleep.call_count == 3
    
    # Khối finally không nên đẩy một kết nối None về pool
    mock_putconn.assert_not_called()

def test_get_db_connection_with_exception(mocker):
    mock_getconn = mocker.patch('database.db_pool.getconn', return_value="fake_connection")
    mock_putconn = mocker.patch('database.db_pool.putconn')

    with pytest.raises(ValueError, match="Fake SQL Error"):
        with database.get_db_connection() as conn:
            raise ValueError("Fake SQL Error")

    mock_getconn.assert_called_once()
    mock_putconn.assert_called_once_with("fake_connection")

class TestDatabaseQueries:
    def test_fetch_product_reviews_from_db(self, mocker):
        mock_getconn = mocker.patch('database.db_pool.getconn')
        mock_putconn = mocker.patch('database.db_pool.putconn')
        
        mock_connection = MagicMock()
        mock_getconn.return_value = mock_connection
        
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
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
        mock_putconn.assert_called_once_with(mock_connection)

    def test_fetch_avg_product_review_score_has_data(self, mocker):
        mock_getconn = mocker.patch('database.db_pool.getconn')
        mock_putconn = mocker.patch('database.db_pool.putconn')
        
        mock_connection = MagicMock()
        mock_getconn.return_value = mock_connection
        
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(4.56,)]

        result = database.fetch_avg_product_review_score_from_db("PROD123")

        assert result == "4.6"
        mock_putconn.assert_called_once_with(mock_connection)

    def test_fetch_avg_product_review_score_no_data(self, mocker):
        mock_getconn = mocker.patch('database.db_pool.getconn')
        mock_putconn = mocker.patch('database.db_pool.putconn')
        
        mock_connection = MagicMock()
        mock_getconn.return_value = mock_connection
        
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(None,)]

        result = database.fetch_avg_product_review_score_from_db("PROD123")

        assert result is None
        mock_putconn.assert_called_once_with(mock_connection)
