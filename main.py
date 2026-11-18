import sys

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        import os
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from label_editor.selftest import run
        sys.exit(run(sys.argv[2]))
    else:
        from label_editor.ui import run_app
        sys.exit(run_app())
