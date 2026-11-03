from app.ocr.engine import calculate_full_hd_size, vote_imei_candidates


def test_calculate_full_hd_size_only_reduces_large_images():
    assert calculate_full_hd_size(2268, 4032) == (1080, 1920)
    assert calculate_full_hd_size(2560, 1440) == (1920, 1080)
    assert calculate_full_hd_size(720, 540) == (720, 540)
    assert calculate_full_hd_size(900, 1200) == (900, 1200)


def test_vote_prefers_35_prefix_for_close_engine_conflict():
    texts = {
        "easy_lines_inv_h80": "IMEI/MEID: 356692119126062",
        "tess_lines_inv_h80": "IMEI/MEID: 256692110126062",
    }

    assert vote_imei_candidates(texts) == ["356692119126062"]


def test_vote_keeps_multiple_imeis_confirmed_by_both_engines():
    text = "IMEI1: 353369280623390 IMEI2: 353369280526718"
    texts = {
        "easy_lines_inv_h80": text,
        "tess_lines_otsu_inv_h80": text,
    }

    assert vote_imei_candidates(texts) == [
        "353369280623390",
        "353369280526718",
    ]


def test_vote_rejects_single_unconfirmed_luhn_match():
    texts = {"easy_full_inv": "358622622212115"}

    assert vote_imei_candidates(texts) == []
