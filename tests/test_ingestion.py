from src.ingestion import ingest_file


def test_csv_ingestion_includes_shape_and_numeric_summary():
    payload = b"region,revenue,orders\nNorth,100,2\nSouth,200,4\n"
    source = ingest_file("sales.csv", payload)

    assert source.source_type == "Table"
    assert source.metadata["rows"] == 2
    assert source.metadata["columns"] == 3
    assert "Numeric summary" in source.content
    assert "North" in source.content


def test_text_ingestion_preserves_content():
    source = ingest_file("brief.txt", b"Review sales performance.\nFlag assumptions.")

    assert source.source_type == "Text"
    assert "Review sales performance" in source.content
    assert "Flag assumptions" in source.content


def test_sqlite_ingestion_reads_tables_in_read_only_mode(tmp_path):
    import sqlite3

    database_path = tmp_path / "source.db"
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE sales (region TEXT, revenue INTEGER)")
    connection.executemany("INSERT INTO sales VALUES (?, ?)", [("North", 100), ("South", 200)])
    connection.commit()
    connection.close()

    source = ingest_file("source.db", database_path.read_bytes())

    assert source.source_type == "SQLite database"
    assert "table: sales" in source.content
    assert source.metadata["tables"]["sales"]["rows"] == 2
