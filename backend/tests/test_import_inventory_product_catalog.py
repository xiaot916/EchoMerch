from pathlib import Path

from scripts.import_inventory_product_catalog import infer_pieces, read_rows


def test_infers_piece_count_from_four_column_store_catalog(tmp_path: Path) -> None:
    source = tmp_path / "catalog.txt"
    source.write_text(
        "系列\t规格\t尺码\t编码\n"
        "大鱼鎏金\t纸尿裤\tNB\tZ125NB60\n"
        "\t\tS\tZ125S58\n"
        "大鱼鎏金2包装\t纸尿裤\tNB\tZ125NB60R2\n",
        encoding="utf-8",
    )

    rows, counters = read_rows(source)

    assert counters["rows"] == 3
    assert rows[0]["pieces"] == 60
    assert rows[1]["series"] == "大鱼鎏金"
    assert rows[2]["pieces"] == 120
    assert rows[2]["display_name"]


def test_preserves_non_diaper_r_suffix_count() -> None:
    assert infer_pieces("BEZ120R3", "柔纸巾120抽", "用品") == 3
