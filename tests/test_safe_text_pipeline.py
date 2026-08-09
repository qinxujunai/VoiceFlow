import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_default_cleaner_does_not_delete_semantic_fillers():
    from text_cleaner import TextCleaner

    cleaner = TextCleaner({"cleaner": {"fix_mistakes": False}})

    assert cleaner.clean("这个就是我们要解决的问题") == "这个就是我们要解决的问题"
    assert cleaner.clean("我的意思就是说不能丢字") == "我的意思就是说不能丢字"


def test_repeated_then_is_the_only_default_filler_cleanup():
    from text_cleaner import TextCleaner

    cleaner = TextCleaner({"cleaner": {"fix_mistakes": False}})

    assert cleaner.clean("然后然后我们继续") == "然后我们继续"


def test_legacy_remove_fillers_flag_cannot_silently_delete_semantic_words():
    from text_cleaner import TextCleaner

    cleaner = TextCleaner(
        {
            "cleaner": {
                "remove_fillers": True,
                "fix_mistakes": False,
            }
        }
    )

    assert cleaner.clean("这个就是原始意思") == "这个就是原始意思"
    source = (SRC / "text_cleaner.py").read_text(encoding="utf-8")
    assert "def _strip_fillers(" not in source
    assert "就是说|然后然后" not in source


def test_final_punctuation_falls_back_if_backend_changes_words():
    from punctuation import FinalPunctuationRestorer

    restorer = FinalPunctuationRestorer(
        backend=lambda _text: "今天天气不好。",
    )

    assert restorer.restore("今天天气很好") == "今天天气很好"


def test_final_punctuation_accepts_punctuation_only_changes():
    from punctuation import FinalPunctuationRestorer

    restorer = FinalPunctuationRestorer(
        backend=lambda _text: "今天，天气很好。",
    )

    assert restorer.restore("今天天气很好") == "今天，天气很好。"


def test_output_handler_has_only_the_clipboard_first_delivery_path():
    source = (SRC / "output_handler.py").read_text(encoding="utf-8")
    delivery = (SRC / "delivery.py").read_text(encoding="utf-8")

    assert "VerifiedClipboard" in source
    assert "DeliveryCoordinator" in source
    assert "clipboard_verified_paste_dispatched" in delivery
    assert "def _type(" not in source
    assert "pyautogui.write(" not in source
