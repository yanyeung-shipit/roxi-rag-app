import sys
import traceback

try:
    from process_to_65_percent_service import main
    main()
except Exception as e:
    with open('processor_error.log', 'w') as f:
        f.write(f"ERROR: {str(e)}\n")
        f.write(f"TRACEBACK:\n{traceback.format_exc()}")
    print(f"Process crashed: {str(e)}")
    sys.exit(1)
